import json
import sqlite3

import pytest

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import AlreadyExistsError, ConstraintError, ValidationError
from melddb.transfer import checksum


def fixture(db):
    db.migrate(Migration("001", (s.collection("docs"), s.table("rows", {"blob": "bytes", "big": "integer"}),
                                s.relationship("links", "docs", "docs"))))
    c = db.collection("docs")
    a, b = c.insert({"v": 1}, id="a"), c.insert({"v": 2}, id="b")
    c.replace("a", {"v": 3})
    db.relationship("links").connect(c.ref(a), c.ref(b), {"weight": 2})
    db.table("rows").insert({"blob": b"\x00\xff", "big": 2**63-1}, id="row")


def test_roundtrip_and_backup(tmp_path):
    source, export = tmp_path / "source.db", tmp_path / "export.json"
    with melddb.open(source) as db:
        fixture(db)
        db.migrate(Migration("002", (s.require("docs", "v"), s.index("docs", "v", unique=True))))
        db.sql("CREATE TABLE external (x INTEGER)")
        db.export(export)
        db.backup(tmp_path / "backup.db")
        with pytest.raises(AlreadyExistsError):
            db.export(export)
        with pytest.raises(AlreadyExistsError):
            db.backup(tmp_path / "backup.db")
    with melddb.open(tmp_path / "restored.db") as db:
        assert db.import_into(export) == {"objects": 3, "records": 4}
        assert db.collection("docs").get("a")["version"] == 2
        assert db.table("rows").get("row")["big"] == 2**63-1
        assert db.table("rows").get("row")["blob"] == b"\x00\xff"
        assert db.check()["ok"]
        assert not db.inspect()["external_tables"]
        with pytest.raises(ConstraintError):
            db.collection("docs").insert({})
        with pytest.raises(AlreadyExistsError):
            db.import_into(export)
    with melddb.open(tmp_path / "backup.db", readonly=True) as db:
        assert db.check()["ok"]
        assert db.inspect()["external_tables"] == ["external"]


def test_corrupt_export_and_invalid_edge_rollback(tmp_path):
    export = tmp_path / "e.json"
    with melddb.open(tmp_path / "s.db") as db:
        fixture(db)
        db.export(export)
    bundle = json.loads(export.read_text())
    bundle["checksum"] = "wrong"
    export.write_text(json.dumps(bundle))
    with melddb.open(tmp_path / "t.db") as db:
        with pytest.raises(ValidationError):
            db.import_into(export)
        assert db.inspect()["objects"] == []
    edge = next(o for o in bundle["payload"]["objects"] if o["schema"]["op"] == "relationship")
    edge["rows"][0]["target_id"] = "missing"
    edge["checksum"] = checksum(edge["rows"])
    bundle["checksum"] = checksum(bundle["payload"])
    export.write_text(json.dumps(bundle))
    with melddb.open(tmp_path / "t.db") as db:
        with pytest.raises(ConstraintError):
            db.import_into(export)
        assert db.inspect()["objects"] == []


def test_external_journal_mode_unchanged(tmp_path):
    path = tmp_path / "external.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE existing (n INTEGER)")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    conn.close()
    with melddb.open(path) as db:
        assert db._backend.conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert not db.inspect()["objects"]
