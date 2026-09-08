"""Atomic, checksum-locked declarations and database-enforced constraints."""
import hashlib
import json

from .backend import quote
from .database import META, MIGRATIONS, physical
from .errors import AlreadyExistsError, MigrationError, UnsupportedError, ValidationError
from .query import json_expr, path_parts
from .schema import Migration
from .storage import TYPES
from .values import encode, text


def create(db, spec):
    be = db._backend
    db._ensure_metadata()
    name = text(spec["name"])
    if not name or name.startswith("_melddb_"):
        raise ValidationError("Invalid managed name")
    prior = be.execute(f"SELECT spec FROM {META} WHERE name=?", (name,))[0]
    if prior:
        old = json.loads(prior[0]["spec"])
        if {k: v for k, v in old.items() if k != "constraints"} == spec:
            return
        raise AlreadyExistsError(f"Different declaration for {name}")
    sqlname = quote(physical(name))
    kind = spec["op"]
    json_type = "JSONB" if be.pg else "TEXT"
    if kind == "collection":
        check = "jsonb_typeof(body)='object'" if be.pg else "json_valid(body) AND json_type(body)='object'"
        be.execute(f"CREATE TABLE {sqlname}(id TEXT PRIMARY KEY NOT NULL, version BIGINT NOT NULL "
                   f"CHECK(version>0), body {json_type} NOT NULL CHECK({check}))")
    elif kind == "table":
        columns = spec.get("columns")
        if not isinstance(columns, dict) or not columns:
            raise ValidationError("Table needs a column mapping")
        declarations = ["id TEXT PRIMARY KEY NOT NULL"]
        for column, typ in columns.items():
            text(column)
            if column == "id" or typ not in TYPES:
                raise ValidationError("Invalid column/type")
            col = quote(column)
            types = {"text": "TEXT", "integer": "BIGINT" if be.pg else "INTEGER",
                     "float": "DOUBLE PRECISION" if be.pg else "REAL",
                     "boolean": "BOOLEAN" if be.pg else "INTEGER",
                     "bytes": "BYTEA" if be.pg else "BLOB"}
            declaration = f"{col} {types[typ]}"
            if not be.pg:
                checks = {"text": f"typeof({col})='text'",
                          "integer": f"typeof({col})='integer'",
                          "float": f"typeof({col}) IN ('integer','real') AND abs({col})<=1.7976931348623157e308",
                          "boolean": f"typeof({col})='integer' AND {col} IN (0,1)",
                          "bytes": f"typeof({col})='blob'"}
                declaration += f" CHECK({col} IS NULL OR ({checks[typ]}))"
            elif typ == "float":
                declaration += f" CHECK({col} IS NULL OR ({col}> '-Infinity'::float8 AND {col}<'Infinity'::float8))"
            declarations.append(declaration)
        be.execute(f"CREATE TABLE {sqlname}({','.join(declarations)})")
    elif kind == "relationship":
        source, target = db._spec(spec["source"]), db._spec(spec["target"])
        if source["op"] == "relationship" or target["op"] == "relationship":
            raise ValidationError("Relationship endpoints must be records")
        if spec.get("on_delete") not in ("restrict", "cascade") or type(spec.get("properties")) is not bool:
            raise ValidationError("Invalid relationship declaration")
        action = spec["on_delete"].upper()
        check = "jsonb_typeof(properties)='object'" if be.pg else (
            "json_valid(properties) AND json_type(properties)='object'")
        if not spec["properties"]:
            check += " AND properties='{}'"
        be.execute(f"CREATE TABLE {sqlname}(source_id TEXT NOT NULL REFERENCES "
                   f"{quote(physical(spec['source']))}(id) ON DELETE {action}, "
                   f"target_id TEXT NOT NULL REFERENCES {quote(physical(spec['target']))}(id) "
                   f"ON DELETE {action}, properties {json_type} NOT NULL CHECK({check}), "
                   "PRIMARY KEY(source_id,target_id))")
        be.execute(f"CREATE INDEX {quote(physical(name)+'_incoming')} ON {sqlname}(target_id,source_id)")
    else:
        raise ValidationError("Unknown declaration")
    if kind in ("collection", "table") and not be.pg:
        be.execute(f"CREATE TRIGGER {quote(physical(name)+'_id')} BEFORE UPDATE OF id ON {sqlname} "
                   "WHEN NEW.id<>OLD.id BEGIN SELECT RAISE(ABORT,'immutable primary key'); END")
    elif kind in ("collection", "table"):
        guard = quote(physical(name) + '_id_guard')
        be.execute(f"CREATE FUNCTION {guard}() RETURNS trigger LANGUAGE plpgsql AS "
                   "'BEGIN IF NEW.id IS DISTINCT FROM OLD.id THEN "
                   "RAISE EXCEPTION ''immutable primary key'' USING ERRCODE = ''23514''; "
                   "END IF; RETURN NEW; END'")
        be.execute(f"CREATE TRIGGER {quote(physical(name)+'_id')} BEFORE UPDATE OF id ON {sqlname} "
                   f"FOR EACH ROW EXECUTE FUNCTION {guard}()")
    db._register(spec)


def add_constraint(db, op):
    be = db._backend
    # The proof adapter intentionally excludes schema evolution, before any mutation.
    if be.pg:
        raise UnsupportedError("PostgreSQL proof does not support constraint/index evolution")
    spec = db._spec(op["name"])
    path = path_parts(op["path"])
    name = quote(physical(op["name"]))
    key = hashlib.sha256(encode(op).encode()).hexdigest()[:24]
    if spec["op"] == "collection":
        val, typ, _ = json_expr(path)
        if op["op"] == "require":
            invalid = f"({typ} IS NULL OR {typ}='null')"
        elif op["op"] == "type":
            kinds = {"string": "'text'", "number": "'integer','real'", "integer": "'integer'",
                     "boolean": "'true','false'"}
            if op["type"] not in kinds:
                raise ValidationError("Supported JSON types: string, number, integer, boolean")
            invalid = f"({typ} IS NOT NULL AND {typ} NOT IN ('null',{kinds[op['type']]}))"
        else:
            invalid = None
        scalar = f"{typ} IN ('text','integer','real','true','false')"
        # A type rank separates false/0 and true/1 while unifying integer/real numbers.
        rank = f"CASE WHEN {typ} IN ('integer','real') THEN 'number' ELSE {typ} END"
        expressions = f"({rank}),({val})"
    elif spec["op"] == "table":
        if len(path) != 1 or path[0] not in spec["columns"]:
            raise ValidationError("Unknown column")
        val = quote(path[0])
        if op["op"] == "type":
            raise UnsupportedError("Table column types are fixed at declaration")
        invalid = f"{val} IS NULL" if op["op"] == "require" else None
        scalar, expressions = f"{val} IS NOT NULL", val
    else:
        raise ValidationError("Constraints apply to record storage")
    violations = []
    if invalid:
        violations = be.execute(f"SELECT id FROM {name} WHERE {invalid} LIMIT 100")[0]
    elif op.get("unique"):
        violations = be.execute(f"SELECT {expressions},COUNT(*) AS count FROM {name} WHERE {scalar} "
                                f"GROUP BY {expressions} HAVING COUNT(*)>1 LIMIT 100")[0]
    if violations:
        raise ValidationError("Existing data violates the proposed constraint (up to 100 shown)", violations)
    if invalid:
        for event in ("INSERT", "UPDATE"):
            be.execute(f"CREATE TRIGGER {quote('ad_rule_'+key+event)} AFTER {event} ON {name} "
                       f"WHEN EXISTS(SELECT 1 FROM {name} WHERE id=NEW.id AND {invalid}) "
                       "BEGIN SELECT RAISE(ABORT,'managed constraint'); END")
    elif op["op"] == "index":
        unique = "UNIQUE" if op.get("unique") else ""
        be.execute(f"CREATE {unique} INDEX {quote('ad_idx_'+key)} ON {name}({expressions}) WHERE {scalar}")
    else:
        raise ValidationError("Unknown constraint operation")
    spec.setdefault("constraints", []).append(op)
    be.execute(f"UPDATE {META} SET spec=? WHERE name=?", (encode(spec), op["name"]))


def apply(db, migrations):
    be = db._backend
    # Validate the full request first so unsupported PG operations cannot partially apply.
    for migration in migrations:
        if not isinstance(migration, Migration) or not text(migration.id):
            raise ValidationError("Expected a named Migration")
        if be.pg and any(op.get("op") not in ("collection", "table", "relationship")
                         for op in migration.operations):
            raise UnsupportedError("PostgreSQL proof supports creation migrations only")
    db._ensure_metadata()
    if be.pg:
        be.execute(f"LOCK TABLE {MIGRATIONS} IN EXCLUSIVE MODE")
    for migration in migrations:
        operations = encode(list(migration.operations))
        checksum = hashlib.sha256(operations.encode()).hexdigest()
        old = be.execute(f"SELECT checksum FROM {MIGRATIONS} WHERE id=?", (migration.id,))[0]
        if old:
            if old[0]["checksum"] != checksum:
                raise MigrationError("Migration checksum drift")
            continue
        latest = be.execute(f"SELECT MAX(id) AS id FROM {MIGRATIONS}")[0][0]["id"]
        if latest is not None and migration.id <= latest:
            raise MigrationError("Migration IDs must increase lexicographically; use zero padding")
        for op in migration.operations:
            if op["op"] in ("collection", "table", "relationship"):
                create(db, op)
            else:
                add_constraint(db, op)
        be.execute(f"INSERT INTO {MIGRATIONS} VALUES (?,?,?)", (migration.id, checksum, operations))
