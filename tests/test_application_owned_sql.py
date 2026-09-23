"""First-class contracts for application-owned SQL objects."""
import json
import sqlite3

import pytest

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import ConstraintError, NotFoundError, TransactionError, UnsupportedError

APPLICATION_OBJECTS = {
    "app_sensor",
    "app_recording",
    "app_recording_tag",
    "app_recording_sensor",
    "app_recording_insert",
}


def install_sqlite_application_schema(path):
    with sqlite3.connect(path, autocommit=True) as raw:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute(
            "CREATE TABLE app_sensor("
            "id TEXT PRIMARY KEY, label TEXT NOT NULL, recording_count INTEGER NOT NULL DEFAULT 0)"
        )
        raw.execute(
            "CREATE TABLE app_recording("
            "id TEXT PRIMARY KEY, sensor_id TEXT NOT NULL REFERENCES app_sensor(id))"
        )
        raw.execute(
            "CREATE TABLE app_recording_tag("
            "recording_id TEXT NOT NULL REFERENCES app_recording(id), "
            "tag TEXT NOT NULL, PRIMARY KEY(recording_id,tag))"
        )
        raw.execute(
            "CREATE INDEX app_recording_sensor ON app_recording(sensor_id)"
        )
        raw.execute(
            "CREATE TRIGGER app_recording_insert AFTER INSERT ON app_recording "
            "BEGIN UPDATE app_sensor SET recording_count=recording_count+1 "
            "WHERE id=NEW.sensor_id; END"
        )
        raw.execute("INSERT INTO app_sensor(id,label) VALUES('sensor-1','')")
        raw.execute("INSERT INTO app_recording VALUES('recording-1','sensor-1')")
        raw.execute("INSERT INTO app_recording_tag VALUES('recording-1','baseline')")


def sqlite_application_schema(path):
    with sqlite3.connect(path) as raw:
        return {
            (kind, name): sql
            for kind, name, sql in raw.execute(
                "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
            )
            if name in APPLICATION_OBJECTS
        }


def install_portable_application_schema(db):
    db.sql("CREATE TABLE app_parent(id TEXT PRIMARY KEY)")
    db.sql(
        "CREATE TABLE app_child("
        "id TEXT PRIMARY KEY, parent_id TEXT NOT NULL REFERENCES app_parent(id))"
    )


def marker(db):
    return "%s" if db.inspect()["backend"] == "postgresql" else "?"


def test_existing_application_schema_is_preserved_and_not_adopted(tmp_path):
    path = tmp_path / "mixed.db"
    install_sqlite_application_schema(path)
    before = sqlite_application_schema(path)

    with melddb.open(path) as db:
        assert set(db.inspect()["external_tables"]) == {
            "app_recording",
            "app_recording_tag",
            "app_sensor",
        }
        db.migrate(Migration("managed-001", (s.collection("docs"),)))

        inspection = db.inspect()
        assert {item["name"] for item in inspection["objects"]} == {"docs"}
        assert set(inspection["external_tables"]) == {
            "app_recording",
            "app_recording_tag",
            "app_sensor",
        }
        with pytest.raises(NotFoundError, match="No managed object"):
            db.table("app_sensor").get("sensor-1")

        assert db.sql(
            "SELECT id,label,recording_count FROM app_sensor", write=False
        ) == [{"id": "sensor-1", "label": "", "recording_count": 1}]
        assert db.sql("SELECT * FROM app_recording_tag", write=False) == [
            {"recording_id": "recording-1", "tag": "baseline"}
        ]
        assert db.check() == {"ok": True, "errors": []}

    assert sqlite_application_schema(path) == before


def test_managed_and_application_writes_share_one_transaction(db):
    install_portable_application_schema(db)
    db.migrate(Migration("managed-001", (s.collection("docs"),)))
    parameter = marker(db)

    with db.transaction() as tx:
        tx.collection("docs").insert({"state": "ready"}, id="doc-1")
        tx.sql(f"INSERT INTO app_parent VALUES ({parameter})", ("parent-1",))
        tx.sql(
            f"INSERT INTO app_child VALUES ({parameter},{parameter})",
            ("child-1", "parent-1"),
        )

    assert db.collection("docs").get("doc-1")["body"] == {"state": "ready"}
    assert db.sql("SELECT * FROM app_child", write=False) == [
        {"id": "child-1", "parent_id": "parent-1"}
    ]


def test_application_constraint_failure_rolls_back_managed_work(db):
    install_portable_application_schema(db)
    db.migrate(Migration("managed-001", (s.collection("docs"),)))
    parameter = marker(db)

    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction() as tx:
            tx.collection("docs").insert({"state": "must-roll-back"}, id="doc-1")
            with pytest.raises(ConstraintError):
                tx.sql(
                    f"INSERT INTO app_child VALUES ({parameter},{parameter})",
                    ("child-1", "missing"),
                )

    assert db.collection("docs").find() == []
    assert db.sql("SELECT * FROM app_child", write=False) == []


def test_postgres_application_sql_proof_and_recovery_boundary(db, tmp_path):
    if db.inspect()["backend"] != "postgresql":
        pytest.skip("PostgreSQL proof requires MELDDB_TEST_POSTGRES")

    install_portable_application_schema(db)
    db.migrate(Migration("managed-001", (s.collection("docs"),)))
    with db.transaction() as tx:
        tx.collection("docs").insert({"backend": "postgresql"}, id="doc-1")
        tx.sql("INSERT INTO app_parent VALUES (%s)", ("parent-1",))
        tx.sql("INSERT INTO app_child VALUES (%s,%s)", ("child-1", "parent-1"))

    assert db.sql("SELECT * FROM app_child", write=False) == [
        {"id": "child-1", "parent_id": "parent-1"}
    ]
    with pytest.raises(UnsupportedError, match="SQLite-only"):
        db.backup(tmp_path / "unsupported.db")


def test_physical_backup_preserves_complete_application_schema(tmp_path, monkeypatch):
    source_path = tmp_path / "mixed.db"
    backup_path = tmp_path / "mixed-backup.db"
    install_sqlite_application_schema(source_path)
    expected_schema = sqlite_application_schema(source_path)
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))

    with melddb.open(source_path, journal_mode="wal") as source:
        source.migrate(Migration("managed-001", (s.collection("docs"),)))
        source.collection("docs").insert({"included": True}, id="doc-1")
        source.backup(backup_path)

    assert sqlite_application_schema(backup_path) == expected_schema
    with melddb.open(backup_path) as restored:
        assert restored.collection("docs").get("doc-1")["body"] == {"included": True}
        assert set(restored.inspect()["external_tables"]) == {
            "app_recording",
            "app_recording_tag",
            "app_sensor",
        }
        assert restored.sql("SELECT * FROM app_recording_tag", write=False) == [
            {"recording_id": "recording-1", "tag": "baseline"}
        ]
        restored.sql("INSERT INTO app_recording VALUES (?,?)", ("recording-2", "sensor-1"))
        assert restored.sql(
            "SELECT recording_count FROM app_sensor WHERE id=?",
            ("sensor-1",),
            write=False,
        ) == [{"recording_count": 2}]
        with pytest.raises(ConstraintError):
            restored.sql(
                "INSERT INTO app_recording_tag VALUES (?,?)",
                ("missing", "invalid"),
            )


def test_logical_transfer_reports_and_omits_application_schema(tmp_path):
    source_path = tmp_path / "mixed.db"
    export_path = tmp_path / "managed.json"
    destination_path = tmp_path / "imported.db"
    install_sqlite_application_schema(source_path)

    with melddb.open(source_path) as source:
        source.migrate(Migration("managed-001", (s.collection("docs"),)))
        source.collection("docs").insert({"included": True}, id="doc-1")
        source.export(export_path)

    bundle = json.loads(export_path.read_text(encoding="utf-8"))
    exclusions = bundle["payload"]["exclusions"]
    assert set(exclusions["external_tables"]) == {
        "app_recording",
        "app_recording_tag",
        "app_sensor",
    }
    assert {(item["type"], item["name"]) for item in exclusions["native_objects"]} >= {
        ("index", "app_recording_sensor"),
        ("trigger", "app_recording_insert"),
    }

    with melddb.open(destination_path) as imported:
        imported.import_into(export_path)
        assert imported.collection("docs").get("doc-1")["body"] == {"included": True}
        assert imported.inspect()["external_tables"] == []
        assert imported.sql(
            "SELECT name FROM sqlite_schema WHERE name LIKE 'app_%'", write=False
        ) == []
