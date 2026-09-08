import os
import subprocess
import sys
from pathlib import Path

import pytest

import melddb


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
