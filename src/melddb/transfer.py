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
    ConstraintError,
    MigrationError,
    UnsupportedError,
    ValidationError,
)
from .migrations import add_constraint, create
from .storage import validate_column
from .values import encode


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
        finally:
            target.close()
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        publish(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return str(destination)


def export(db, destination):
    be = db._backend
    description = db._inspect()
    objects = []
    for obj in description["objects"]:
        spec = obj["schema"]
        order = "source_id,target_id" if spec["op"] == "relationship" else "id"
        rows = be.execute(f"SELECT * FROM {quote(obj['physical'])} ORDER BY {order}")[0]
        for row in rows:
            if spec["op"] in ("collection", "relationship"):
                key = "body" if spec["op"] == "collection" else "properties"
                if isinstance(row[key], str):
                    row[key] = json.loads(row[key])
            else:
                for col, kind in spec["columns"].items():
                    if row[col] is not None:
                        if kind == "bytes":
                            row[col] = {"base64": base64.b64encode(row[col]).decode("ascii")}
                        elif kind == "boolean":
                            row[col] = bool(row[col])
        objects.append({"schema": spec, "rows": rows, "checksum": checksum(rows)})
    payload = {"format": 1, "objects": objects, "migrations": description["migrations"],
               "exclusions": {"external_tables": description["external_tables"],
                              "native_objects": "External indexes, views, triggers and native logic are not exported"}}
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
    if be.tables():
        raise AlreadyExistsError("Import requires an empty database/schema")
    try:
        bundle = json.loads(Path(source).read_text(encoding="utf-8"))
        payload = bundle["payload"]
        if payload["format"] != 1 or checksum(payload) != bundle["checksum"]:
            raise ValidationError("Unsupported format or checksum mismatch")
        objects = payload["objects"]
        names = [obj["schema"]["name"] for obj in objects]
        if len(names) != len(set(names)):
            raise ValidationError("Duplicate logical storage name")
        for obj in objects:
            if checksum(obj["rows"]) != obj["checksum"]:
                raise ValidationError("Object checksum mismatch")
            spec = obj["schema"]
            if be.pg and spec.get("constraints"):
                raise UnsupportedError("PostgreSQL proof cannot import evolved constraints")
        for migration in payload["migrations"]:
            if hashlib.sha256(migration["operations"].encode()).hexdigest() != migration["checksum"]:
                raise MigrationError("Migration checksum mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Malformed logical export") from exc
    db._ensure_metadata()
    # Endpoints first, edges second. Logical names survive changes of physical representation.
    objects = sorted(objects, key=lambda obj: obj["schema"]["op"] == "relationship")
    for obj in objects:
        spec = obj["schema"]
        create(db, {key: value for key, value in spec.items() if key != "constraints"})
        for row in obj["rows"]:
            record = dict(row)
            if spec["op"] == "collection":
                if set(row) != {"id", "version", "body"} or type(row["version"]) is not int or row["version"] < 1:
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
                            record[col] = base64.b64decode(row[col]["base64"], validate=True)
                        except (KeyError, TypeError, ValueError) as exc:
                            raise ValidationError("Invalid binary encoding") from exc
                    validate_column(kind, record[col])
            else:
                raise ValidationError("Unsupported managed object")
            from .values import text
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
