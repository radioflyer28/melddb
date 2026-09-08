"""Versioned logical snapshots and no-overwrite backups."""
import base64
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path

from .backend import quote
from .database import MIGRATIONS, physical
from .errors import (
    AlreadyExistsError,
    ConnectionError,
    ConstraintError,
    MigrationError,
    UnsupportedError,
    ValidationError,
)
from .migrations import add_constraint, create, validate_operation
from .storage import validate_column
from .values import encode, text


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValidationError("Invalid logical artifact fields")


def native_exclusions(be):
    if be.pg:
        # Physical indexes/triggers/functions are recreated from managed schema;
        # name every native object omitted from this data-oriented artifact.
        return be.execute("SELECT 'relation' AS type,c.relname AS name FROM pg_class c "
                          "WHERE c.relnamespace=current_schema()::regnamespace AND c.relkind NOT IN ('r','p') "
                          "UNION ALL SELECT 'function',p.proname FROM pg_proc p "
                          "WHERE p.pronamespace=current_schema()::regnamespace "
                          "UNION ALL SELECT 'trigger',t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                          "WHERE c.relnamespace=current_schema()::regnamespace AND NOT t.tgisinternal "
                          "ORDER BY type,name")[0]
    return be.execute("SELECT type,name FROM sqlite_schema WHERE type IN ('index','view','trigger') "
                      "AND name NOT LIKE 'sqlite_%' ORDER BY type,name")[0]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def publish(temp, destination):
    # A hard link atomically creates a new name and fails if it already exists.
    try:
        os.link(temp, destination)
    except FileExistsError as exc:
        raise AlreadyExistsError("Destination already exists") from exc


def backup(db, destination):
    if db._backend.pg:
        raise UnsupportedError("Physical backup is SQLite-only")
    destination = Path(destination)
    if destination.exists():
        raise AlreadyExistsError("Backup destination already exists")
    temp = destination.with_name(destination.name + ".partial-" + uuid.uuid4().hex)
    try:
        target = sqlite3.connect(temp, autocommit=True)
        try:
            db._backend.conn.backup(target)
            if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ConstraintError("Backup integrity check failed")
            if target.execute("PRAGMA foreign_key_check").fetchall():
                raise ConstraintError("Backup contains invalid references")
            # The detached artifact has no live writers. Make it standalone
            # before reopening it for validation or publishing its main file.
            target.execute("PRAGMA journal_mode=DELETE")
        finally:
            target.close()
        from .database import Database
        with Database(temp, readonly=True) as restored:
            if not restored.check()["ok"]:
                raise ConstraintError("Backup managed structure validation failed")
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        publish(temp, destination)
    except sqlite3.Error as exc:
        raise ConnectionError("SQLite backup creation or validation failed") from exc
    finally:
        temp.unlink(missing_ok=True)
    return str(destination)


def export(db, destination):
    be = db._backend
    if not db._check()["ok"]:
        raise ConstraintError("Cannot export inconsistent managed storage")
    description = db._inspect()
    objects = []
    for obj in description["objects"]:
        spec = obj["schema"]
        order = "source_id,target_id" if spec["op"] == "relationship" else "id"
        rows = be.execute(f"SELECT * FROM {quote(obj['physical'])} ORDER BY {order}")[0]
        for row in rows:
            for identity in ("source_id", "target_id") if spec["op"] == "relationship" else ("id",):
                text(row[identity])
            if spec["op"] in ("collection", "relationship"):
                key = "body" if spec["op"] == "collection" else "properties"
                if isinstance(row[key], str):
                    row[key] = json.loads(row[key])
                encode(row[key], object_only=True)
                if spec["op"] == "collection" and (type(row["version"]) is not int or
                                                      not 1 <= row["version"] <= 2**63-1):
                    raise ValidationError("Invalid stored document version")
            else:
                for col, kind in spec["columns"].items():
                    if row[col] is not None:
                        if kind == "bytes":
                            row[col] = {"base64": base64.b64encode(row[col]).decode("ascii")}
                        elif kind == "boolean":
                            row[col] = bool(row[col])
                        else:
                            validate_column(kind, row[col])
        objects.append({"schema": spec, "rows": rows, "checksum": checksum(rows)})
    payload = {"format": 1, "objects": objects, "migrations": description["migrations"],
               "exclusions": {"external_tables": description["external_tables"],
                              "native_objects": native_exclusions(be)}}
    bundle = {"payload": payload, "checksum": checksum(payload)}
    destination = Path(destination)
    if destination.exists():
        raise AlreadyExistsError("Export destination already exists")
    temp = destination.with_name(destination.name + ".partial-" + uuid.uuid4().hex)
    try:
        with temp.open("xb") as stream:
            stream.write(canonical(bundle))
            stream.flush()
            os.fsync(stream.fileno())
        publish(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return str(destination)


def import_into(db, source):
    be = db._backend
    native = (be.execute("SELECT 1 FROM pg_class WHERE relnamespace=current_schema()::regnamespace "
                         "UNION ALL SELECT 1 FROM pg_proc WHERE pronamespace=current_schema()::regnamespace")[0]
              if be.pg else be.execute("SELECT 1 FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'")[0])
    if native:
        raise AlreadyExistsError("Import requires an empty database/schema")
    try:
        bundle = json.loads(Path(source).read_text(encoding="utf-8"),
                            object_pairs_hook=strict_object, parse_constant=invalid_constant)
        fields(bundle, ("payload", "checksum"))
        payload = bundle["payload"]
        fields(payload, ("format", "objects", "migrations", "exclusions"))
        if type(payload["format"]) is not int or payload["format"] != 1 or checksum(payload) != bundle["checksum"]:
            raise ValidationError("Unsupported format or checksum mismatch")
        fields(payload["exclusions"], ("external_tables", "native_objects"))
        if not isinstance(payload["exclusions"]["external_tables"], list):
            raise ValidationError("Invalid exclusions")
        for excluded in payload["exclusions"]["external_tables"]:
            text(excluded)
        native_objects = payload["exclusions"]["native_objects"]
        if isinstance(native_objects, str):
            text(native_objects)  # Earlier format-1 alpha exports used a description.
        elif isinstance(native_objects, list):
            for item in native_objects:
                fields(item, ("type", "name"))
                text(item["type"])
                text(item["name"])
        else:
            raise ValidationError("Invalid native-object exclusions")
        objects = payload["objects"]
        if not isinstance(objects, list) or not isinstance(payload["migrations"], list):
            raise ValidationError("Objects and migrations must be lists")
        for obj in objects:
            fields(obj, ("schema", "rows", "checksum"))
            if not isinstance(obj["schema"], dict) or not isinstance(obj["rows"], list):
                raise ValidationError("Invalid object schema or rows")
            spec = obj["schema"]
            validate_operation({k: v for k, v in spec.items() if k != "constraints"})
            if spec["op"] not in ("collection", "table", "relationship"):
                raise ValidationError("Expected storage declaration")
            if not isinstance(spec.get("constraints", []), list):
                raise ValidationError("Invalid constraint list")
            for rule in spec.get("constraints", []):
                validate_operation(rule)
                if rule["op"] not in ("require", "type", "index") or rule["name"] != spec["name"]:
                    raise ValidationError("Invalid constraint target or operation")
        names = [obj["schema"]["name"] for obj in objects]
        if len(names) != len(set(names)):
            raise ValidationError("Duplicate logical storage name")
        schemas = {obj["schema"]["name"]: obj["schema"] for obj in objects}
        for obj in objects:
            if checksum(obj["rows"]) != obj["checksum"]:
                raise ValidationError("Object checksum mismatch")
            spec = obj["schema"]
            if be.pg and spec.get("constraints"):
                raise UnsupportedError("PostgreSQL proof cannot import evolved constraints")
        previous = None
        for migration in payload["migrations"]:
            fields(migration, ("id", "checksum", "operations"))
            ident = text(migration["id"])
            if not ident or (previous is not None and ident <= previous):
                raise MigrationError("Migration IDs must be unique and ordered")
            previous = ident
            operations = json.loads(text(migration["operations"]), object_pairs_hook=strict_object,
                                    parse_constant=invalid_constant)
            if not isinstance(operations, list):
                raise ValidationError("Migration operations must be a list")
            for op in operations:
                validate_operation(op)
                declared = schemas.get(op["name"])
                if declared is None:
                    raise MigrationError("Migration targets absent storage")
                if op["op"] in ("collection", "table", "relationship"):
                    if op != {k: v for k, v in declared.items() if k != "constraints"}:
                        raise MigrationError("Migration disagrees with exported schema")
                elif op not in declared.get("constraints", []):
                    raise MigrationError("Migration constraint missing from exported schema")
                if be.pg and op["op"] not in ("collection", "table", "relationship"):
                    raise UnsupportedError("PostgreSQL proof imports creation-only revisions")
            if hashlib.sha256(migration["operations"].encode()).hexdigest() != migration["checksum"]:
                raise MigrationError("Migration checksum mismatch")
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise ValidationError("Malformed logical export") from exc
    db._ensure_metadata()
    # Endpoints first, edges second. Logical names survive changes of physical representation.
    objects = sorted(objects, key=lambda obj: obj["schema"]["op"] == "relationship")
    for obj in objects:
        spec = obj["schema"]
        create(db, {key: value for key, value in spec.items() if key != "constraints"})
        for row in obj["rows"]:
            if not isinstance(row, dict):
                raise ValidationError("Record must be an object")
            record = dict(row)
            if spec["op"] == "collection":
                if (set(row) != {"id", "version", "body"} or type(row["version"]) is not int or
                        not 1 <= row["version"] <= 2**63-1):
                    raise ValidationError("Invalid document envelope")
                record["body"] = encode(row["body"], object_only=True)
            elif spec["op"] == "relationship":
                if set(row) != {"source_id", "target_id", "properties"}:
                    raise ValidationError("Invalid relationship record")
                record["properties"] = encode(row["properties"], object_only=True)
            elif spec["op"] == "table":
                if set(row) != {"id", *spec["columns"]}:
                    raise ValidationError("Invalid table record")
                for col, kind in spec["columns"].items():
                    if kind == "bytes" and row[col] is not None:
                        try:
                            fields(row[col], ("base64",))
                            record[col] = base64.b64decode(row[col]["base64"], validate=True)
                            if base64.b64encode(record[col]).decode("ascii") != row[col]["base64"]:
                                raise ValidationError("Noncanonical binary encoding")
                        except (KeyError, TypeError, ValueError) as exc:
                            raise ValidationError("Invalid binary encoding") from exc
                    validate_column(kind, record[col])
            else:
                raise ValidationError("Unsupported managed object")
            for key in ("source_id", "target_id") if spec["op"] == "relationship" else ("id",):
                text(record[key])
            cols = list(record)
            be.execute(f"INSERT INTO {quote(physical(spec['name']))} "
                       f"({','.join(quote(c) for c in cols)}) VALUES ({','.join('?' for _ in cols)})",
                       list(record.values()))
        for constraint in spec.get("constraints", []):
            if constraint["name"] != spec["name"]:
                raise ValidationError("Constraint targets a different object")
            add_constraint(db, constraint)
    for migration in payload["migrations"]:
        be.execute(f"INSERT INTO {MIGRATIONS} VALUES (?,?,?)",
                   (migration["id"], migration["checksum"], migration["operations"]))
    result = db._check()
    if not result["ok"]:
        raise ConstraintError("Imported database failed consistency checks")
    return {"objects": len(objects), "records": sum(len(o["rows"]) for o in objects)}
