"""Read-only verification of managed SQLite structures against their declarations."""
import hashlib
import json

from .backend import quote
from .errors import MeldDBError, ValidationError
from .values import encode


def structural_errors(db):
    from .database import META, MIGRATIONS, VERSION, Database, physical
    from .migrations import add_constraint, create, validate_operation

    be = db._backend
    errors = []
    try:
        description = db._inspect()
        for revision in description["migrations"]:
            operations = json.loads(revision["operations"])
            if not isinstance(operations, list):
                raise ValueError("Migration operations must be a list")
            for operation in operations:
                validate_operation(operation)
            checksum = hashlib.sha256(encode(operations).encode()).hexdigest()
            if checksum != revision["checksum"]:
                errors.append({"code": "migration_checksum", "id": revision["id"]})
        if be.pg:
            for obj in description["objects"]:
                if not be.exists(obj["physical"]):
                    errors.append({"code": "missing_table", "name": obj["physical"]})
            return errors
        if not be.exists(META):
            return errors
        # Reuse supported DDL generation in an isolated, empty database. No user
        # rows are copied and no repair is applied to the inspected database.
        with Database(":memory:") as expected:
            with expected.transaction():
                expected._ensure_metadata()
                objects = sorted(description["objects"], key=lambda o: o["schema"]["op"] == "relationship")
                for obj in objects:
                    spec = obj["schema"]
                    if obj["name"] != spec["name"] or obj["physical"] != physical(obj["name"]):
                        errors.append({"code": "physical_mapping", "name": obj["name"]})
                    declaration = {k: v for k, v in spec.items() if k != "constraints"}
                    if spec["op"] == "table":
                        # Canonical metadata JSON sorts column keys. Preserve the
                        # actual order of known columns when regenerating DDL;
                        # definitions and missing/extra columns are still checked.
                        columns = spec["columns"]
                        order = [r["name"] for r in be.execute(
                            f"PRAGMA table_info({quote(physical(obj['name']))})")[0]]
                        declaration["columns"] = {k: columns[k] for k in [*order, *columns] if k in columns}
                    create(expected, declaration)
                for obj in objects:
                    for rule in obj["schema"].get("constraints", []):
                        if rule["name"] != obj["name"]:
                            raise ValueError("Constraint targets a different object")
                        add_constraint(expected, rule)
                        try:
                            add_constraint(db, rule, validate_only=True)
                        except ValidationError as exc:
                            errors.append({"code": "constraint_data", "name": obj["name"],
                                           "message": str(exc), "violations": exc.violations})
            wanted = expected._backend.execute("SELECT name,type,tbl_name,sql FROM sqlite_schema")[0]
        actual = {row["name"]: row for row in be.execute(
            "SELECT name,type,tbl_name,sql FROM sqlite_schema")[0]}
        expected_names = {row["name"] for row in wanted}
        managed = {physical(obj["name"]) for obj in objects} | {META, MIGRATIONS, VERSION}
        for row in wanted:
            found = actual.get(row["name"])
            if found is None:
                errors.append({"code": "missing_structure", "name": row["name"], "type": row["type"]})
            elif found != row:
                errors.append({"code": "changed_structure", "name": row["name"], "type": row["type"]})
        for row in actual.values():
            if row["type"] == "trigger" and row["tbl_name"] in managed and row["name"] not in expected_names:
                errors.append({"code": "unexpected_trigger", "name": row["name"]})
    except (MeldDBError, ValueError, TypeError, KeyError) as exc:
        errors.append({"code": "invalid_metadata", "message": str(exc)})
    return errors
