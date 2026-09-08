import os
import subprocess
import sys
from pathlib import Path

import pytest

import melddb
from melddb import Migration
from melddb import schema as s


def child(path, action, *args):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / "src"))
    return subprocess.run([sys.executable, str(Path(__file__).with_name("crash_worker.py")),
                           str(path), action, *map(str, args)], env=env,
                          capture_output=True, timeout=30)


@pytest.mark.parametrize("action,expected", [("transaction-before", False), ("transaction-after", True)])
def test_commit_boundary(tmp_path, action, expected):
    path = tmp_path / "db"
    with melddb.open(path) as db:
        db.collection("docs").insert({}, id="original")
    result = child(path, action)
    assert result.returncode == 73, result.stderr
    with melddb.open(path) as db:
        assert bool(db.collection("docs").get("new")) is expected
        assert db.collection("docs").get("original")
        assert db.check()["ok"]


def test_interrupted_migration_and_import(tmp_path):
    path, exported = tmp_path / "db", tmp_path / "export.json"
    result = child(path, "migration")
    assert result.returncode == 73, result.stderr
    with melddb.open(path) as db:
        assert db.inspect()["objects"] == []
        assert db.check()["ok"]
    with melddb.open(tmp_path / "source") as db:
        db.collection("docs").insert({})
        db.export(exported)
    result = child(path, "import", exported)
    assert result.returncode == 73, result.stderr
    with melddb.open(path) as db:
        assert db.inspect()["objects"] == []
        assert db.check()["ok"]
        db.import_into(exported)


def test_interrupted_backup(tmp_path):
    path, backup = tmp_path / "db", tmp_path / "backup"
    with melddb.open(path) as db:
        db.collection("docs").insert({"text": "x" * 100000})
    result = child(path, "backup", backup)
    assert result.returncode == 73, result.stderr
    assert not backup.exists()
    with melddb.open(path) as db:
        db.backup(backup)
    with melddb.open(backup) as db:
        assert db.check()["ok"]


def test_cross_process_writer_contention(tmp_path):
    path = tmp_path / "db"
    with melddb.open(path) as db:
        db.collection("docs").insert({})
        with db.transaction() as tx:
            tx.collection("docs").insert({})
            result = child(path, "busy")
            assert result.returncode == 74, result.stderr


@pytest.mark.parametrize("checkpoint", ["trigger", "index", "metadata", "revision", "commit"])
def test_evolution_crash_and_retry(tmp_path, checkpoint):
    path = tmp_path / "evolution"
    revision = Migration("002", (s.require("docs", "key"), s.type_of("docs", "key", type="string"),
                                  s.index("docs", "key", unique=True)))
    with melddb.open(path) as db:
        db.migrate(Migration("001", (s.collection("docs"),)))
        db.collection("docs").insert({"key": "original"}, id="original")
        before = db.sql("SELECT name,sql FROM sqlite_schema ORDER BY name")
    result = child(path, "evolution", checkpoint)
    assert result.returncode == 73, result.stderr
    with melddb.open(path) as db:
        assert len(db.inspect()["migrations"]) == (2 if checkpoint == "commit" else 1)
        if checkpoint != "commit":
            assert db.sql("SELECT name,sql FROM sqlite_schema ORDER BY name") == before
        assert db.collection("docs").get("original")["body"] == {"key": "original"}
        assert db.check()["ok"]
        db.migrate(revision)
        with pytest.raises(melddb.errors.ConstraintError):
            db.collection("docs").insert({})
        with pytest.raises(melddb.errors.AlreadyExistsError):
            db.collection("docs").insert({"key": "original"})


def test_constraint_validation_holds_write_lock(tmp_path, monkeypatch):
    path = tmp_path / "locked"
    with melddb.open(path) as db:
        db.collection("docs").insert({"key": "original"})
        execute = db._backend.execute
        checked = []
        def interleaved(sql, *args, **kwargs):
            result = execute(sql, *args, **kwargs)
            if sql.startswith("SELECT id FROM"):
                writer = child(path, "busy")
                assert writer.returncode == 74, writer.stderr
                checked.append(True)
            return result
        monkeypatch.setattr(db._backend, "execute", interleaved)
        db.migrate(Migration("001", (s.require("docs", "key"),)))
        assert checked
        assert len(db.collection("docs").find()) == 1


@pytest.mark.parametrize("action,published", [("backup-before-publish", False), ("backup-after-publish", True)])
def test_backup_publication_crash(tmp_path, action, published):
    path, destination = tmp_path / "source", tmp_path / "restored"
    with melddb.open(path) as db:
        db.collection("docs").insert({"value": "committed"}, id="original")
    result = child(path, action, destination)
    assert result.returncode == 73, result.stderr
    assert destination.exists() is published
    if not published:
        with melddb.open(path) as db:
            db.backup(destination)
    with melddb.open(destination) as restored:
        assert restored.check()["ok"]
        assert restored.collection("docs").get("original")["body"] == {"value": "committed"}
