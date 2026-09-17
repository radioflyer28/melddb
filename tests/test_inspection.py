"""S09 structural drift, validated backup restoration, and read-only CLI."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import AlreadyExistsError, ConstraintError


def populate(path):
    with melddb.open(path) as db:
        db.migrate(Migration("001", (s.collection("docs"), s.table("rows", {"value": "bytes"}),
                                     s.relationship("links", "docs", "rows", on_delete="cascade"))))
        with db.transaction() as tx:
            doc = tx.collection("docs").insert({"key": "original"}, id="doc")
            row = tx.table("rows").insert({"value": b"\x00\xff"}, id="row")
            tx.relationship("links").connect(tx.collection("docs").ref(doc), tx.table("rows").ref(row))
        db.migrate(Migration("002", (s.require("docs", "key"), s.index("docs", "key", unique=True))))
        return {o["name"]: o["physical"] for o in db.inspect()["objects"]}


@pytest.mark.parametrize("damage,code", [("trigger", "missing_structure"), ("index", "missing_structure"),
    ("table", "missing_structure"), ("column", "changed_structure"), ("replacement", "changed_structure"),
    ("extra_trigger", "unexpected_trigger"), ("mapping", "physical_mapping"),
    ("checksum", "migration_checksum"), ("json", "invalid_metadata")])
def test_structural_drift(tmp_path, damage, code):
    path = tmp_path / "source.db"
    names = populate(path)
    with sqlite3.connect(path, autocommit=True) as raw:
        if damage in ("trigger", "index"):
            prefix = "ad_rule_%" if damage == "trigger" else "ad_idx_%"
            name = raw.execute("SELECT name FROM sqlite_schema WHERE name LIKE ?", (prefix,)).fetchone()[0]
            raw.execute(f'DROP {damage.upper()} "{name}"')
        elif damage == "table":
            raw.execute(f'DROP TABLE "{names["links"]}"')
        elif damage == "column":
            raw.execute(f'ALTER TABLE "{names["rows"]}" ADD COLUMN extra TEXT')
        elif damage == "replacement":
            name = raw.execute("SELECT name FROM sqlite_schema WHERE name LIKE 'ad_rule_%'").fetchone()[0]
            raw.execute(f'DROP TRIGGER "{name}"')
            raw.execute(f'CREATE TRIGGER "{name}" AFTER INSERT ON "{names["docs"]}" BEGIN SELECT 1; END')
        elif damage == "extra_trigger":
            raw.execute(f'CREATE TRIGGER surprise AFTER INSERT ON "{names["docs"]}" BEGIN SELECT 1; END')
        elif damage == "mapping":
            raw.execute("UPDATE _melddb_objects SET physical='wrong' WHERE name='docs'")
        elif damage == "checksum":
            raw.execute("UPDATE _melddb_migrations SET checksum='wrong'")
        else:
            raw.execute("UPDATE _melddb_objects SET spec='{' WHERE name='docs'")
        before = raw.execute("SELECT name,sql FROM sqlite_schema ORDER BY name").fetchall()
    with melddb.open(path, readonly=True) as db:
        result = db.check()
        assert not result["ok"]
        assert code in {e.get("code") for e in result["errors"]}
        with pytest.raises(ConstraintError):
            db.backup(tmp_path / "rejected.db")
    assert not (tmp_path / "rejected.db").exists()
    assert not list(tmp_path.glob("*.partial-*"))
    with sqlite3.connect(path, autocommit=True) as raw:
        assert raw.execute("SELECT name,sql FROM sqlite_schema ORDER BY name").fetchall() == before


def test_backup_restore_live_wal_and_external_storage(tmp_path, monkeypatch):
    path, backup = tmp_path / "source.db", tmp_path / "restored.db"
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    names = populate(path)
    with melddb.open(path, journal_mode="wal") as source:
        source.sql("CREATE TABLE external_log(message TEXT)")
        source.sql("INSERT INTO external_log VALUES (?)", ("preserved",))
        source.sql(f'CREATE INDEX extra_lookup ON "{names["rows"]}"(value)')
        source.collection("docs").replace("doc", {"key": "new"})
        assert source.check()["ok"]
        source.backup(backup)
        assert source._backend.conn.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert not list(tmp_path.glob("*.partial-*"))
        with pytest.raises(AlreadyExistsError):
            source.backup(backup)
        with melddb.open(backup) as restored:
            assert restored.check()["ok"]
            assert restored.collection("docs").get("doc")["version"] == 2
            assert restored.table("rows").get("row")["value"] == b"\x00\xff"
            assert len(restored.relationship("links").edges(restored.collection("docs").ref("doc"))) == 1
            assert restored.sql("SELECT * FROM external_log") == [{"message": "preserved"}]
            restored.collection("docs").replace("doc", {"key": "independent"})
        assert source.collection("docs").get("doc")["body"] == {"key": "new"}


def cli(*args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    return subprocess.run([sys.executable, "-m", "melddb.cli", *map(str, args)], env=env,
                          capture_output=True, text=True, timeout=30)


def test_cli_is_read_only_and_reports_errors(tmp_path):
    path = tmp_path / "source.db"
    populate(path)
    before = path.read_bytes()
    for operation in ("inspect", "check"):
        result = cli(operation, path)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)
        assert path.read_bytes() == before
    missing = tmp_path / "missing.db"
    assert cli("inspect", missing).returncode == 1
    assert not missing.exists()
    bad_args = cli("check", path, "extra")
    assert bad_args.returncode == 2 and "Traceback" not in bad_args.stderr
    with sqlite3.connect(path, autocommit=True) as raw:
        raw.execute("DROP TRIGGER " + raw.execute(
            "SELECT name FROM sqlite_schema WHERE type='trigger'").fetchone()[0])
    result = cli("check", path)
    assert result.returncode == 1 and not json.loads(result.stdout)["ok"]


def test_cli_backup_restore_and_io_failure(tmp_path):
    path = tmp_path / "source.db"
    populate(path)
    backup = tmp_path / "backup.db"
    result = cli("backup", path, backup)
    assert result.returncode == 0, result.stderr
    assert cli("check", backup).returncode == 0
    result = cli("export", path, tmp_path / "missing" / "export.json")
    assert result.returncode == 1 and "Traceback" not in result.stderr
    result = cli("backup", path, tmp_path / "missing" / "backup.db")
    assert result.returncode == 1 and "Traceback" not in result.stderr


def test_restored_trigger_does_not_hide_invalid_existing_data(tmp_path):
    path = tmp_path / "bad-data.db"
    names = populate(path)
    with sqlite3.connect(path, autocommit=True) as raw:
        triggers = raw.execute("SELECT name,sql FROM sqlite_schema WHERE name LIKE 'ad_rule_%'").fetchall()
        for name, _ in triggers:
            raw.execute(f'DROP TRIGGER "{name}"')
        raw.execute(f'UPDATE "{names["docs"]}" SET body=\'{{}}\'')
        for _, statement in triggers:
            raw.execute(statement)
    with melddb.open(path) as db:
        errors = db.check()["errors"]
        assert any(e.get("code") == "constraint_data" and e["violations"][0]["id"] == "doc" for e in errors)


def test_backup_validates_snapshot_before_publish(tmp_path, monkeypatch):
    from melddb import transfer
    path, destination = tmp_path / "source.db", tmp_path / "backup.db"
    populate(path)
    original = transfer.publish
    def racing_publish(temp, target):
        target.write_bytes(b"another artifact")
        return original(temp, target)
    monkeypatch.setattr(transfer, "publish", racing_publish)
    with melddb.open(path) as db:
        with pytest.raises(AlreadyExistsError):
            db.backup(destination)
    assert destination.read_bytes() == b"another artifact"
    assert not list(tmp_path.glob("*.partial-*"))
