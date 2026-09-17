import sqlite3
import threading

import pytest

import melddb
from melddb.errors import (
    BusyError,
    OwnershipError,
    TransactionError,
    UnsupportedError,
    ValidationError,
)

FIXED_VERSIONS = [(3, 44, 6), (3, 50, 7), (3, 51, 3), (3, 53, 1)]
UNSAFE_VERSIONS = [(3, 44, 5), (3, 49, 1), (3, 50, 4), (3, 51, 2)]


@pytest.mark.parametrize("version", FIXED_VERSIONS)
def test_fixed_wal_runtimes_are_accepted(tmp_path, monkeypatch, version):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    with melddb.open(tmp_path / "fixed.db", journal_mode="wal") as db:
        assert db.sqlite_runtime()["journal_mode"] == "wal"


@pytest.mark.parametrize("version", UNSAFE_VERSIONS)
def test_unsafe_wal_runtimes_fail_before_file_creation(tmp_path, monkeypatch, version):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    path = tmp_path / "unsafe.db"
    with pytest.raises(UnsupportedError, match="WAL-reset"):
        melddb.open(path, journal_mode="wal")
    assert not path.exists()


def test_unsafe_runtime_defaults_new_database_to_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 4))
    path = tmp_path / "default.db"
    with melddb.open(path) as db:
        assert db.sqlite_runtime()["journal_mode"] == "delete"
    with melddb.open(path, journal_mode="delete"):
        pass


def test_unsafe_runtime_rejects_preserved_existing_wal(tmp_path, monkeypatch):
    path = tmp_path / "existing.db"
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    with melddb.open(path, journal_mode="wal"):
        pass
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 4))
    with pytest.raises(UnsupportedError, match="WAL-reset"):
        melddb.open(path)


def test_existing_database_can_change_journal_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    path = tmp_path / "journal.db"
    sqlite3.connect(path).close()
    with melddb.open(path, journal_mode="wal") as db:
        assert db.sqlite_runtime()["journal_mode"] == "wal"
    with melddb.open(path, journal_mode="delete") as db:
        assert db.sqlite_runtime()["journal_mode"] == "delete"


def test_readonly_journal_selection_is_an_assertion(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    path = tmp_path / "readonly.db"
    with melddb.open(path, journal_mode="delete"):
        pass
    with melddb.open(path, readonly=True, journal_mode="delete") as db:
        assert db.sqlite_runtime()["journal_mode"] == "delete"
    with pytest.raises(UnsupportedError, match="read-only"):
        melddb.open(path, readonly=True, journal_mode="wal")
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)


@pytest.mark.parametrize("mode", ["truncate", "WAL", 1, False])
def test_invalid_journal_selection_is_rejected(tmp_path, mode):
    with pytest.raises(ValidationError, match="journal_mode"):
        melddb.open(tmp_path / "invalid.db", journal_mode=mode)


def test_memory_database_rejects_file_journal_selection():
    with pytest.raises(UnsupportedError, match="file-backed"):
        melddb.open(":memory:", journal_mode="delete")


def test_runtime_report_is_effective_plain_data(tmp_path):
    with melddb.open(tmp_path / "runtime.db", journal_mode="delete") as db:
        report = db.sqlite_runtime()
        assert report["backend"] == "sqlite"
        assert report["sqlite_version"] == sqlite3.sqlite_version
        assert report["file_backed"] is True
        assert report["readonly"] is False
        assert report["journal_mode"] == "delete"
        assert report["synchronous"] == 2
        assert report["foreign_keys"] is True
        assert set(report["capabilities"]) == {"wal", "statistics", "checkpoint"}
        report["capabilities"]["wal"]["available"] = "changed"
        assert db.sqlite_runtime()["capabilities"]["wal"]["available"] is False


def test_memory_runtime_reports_file_capabilities_unavailable():
    with melddb.open(":memory:") as db:
        report = db.sqlite_runtime()
        assert report["file_backed"] is False
        assert report["journal_mode"] == "memory"
        assert report["capabilities"]["statistics"]["available"] is False
        assert report["capabilities"]["checkpoint"]["available"] is False


def test_postgres_rejects_sqlite_runtime_interface(tmp_path):
    with melddb.open(tmp_path / "sqlite.db", journal_mode="delete") as db:
        db._backend.pg = True
        try:
            with pytest.raises(UnsupportedError, match="SQLite"):
                db.sqlite_runtime()
        finally:
            db._backend.pg = False


def test_statistics_maintenance_is_structured_and_persistent(tmp_path):
    path = tmp_path / "statistics.db"
    with melddb.open(path, journal_mode="delete") as db:
        db.sql("CREATE TABLE sample(value INTEGER)")
        db.sql("CREATE INDEX sample_value ON sample(value)")
        db.sql("INSERT INTO sample VALUES(1),(2),(3)")
        optimized = db.maintain_sqlite(checkpoint=None)
        assert optimized == {
            "statistics": {"action": "optimize", "completed": True},
            "checkpoint": None,
        }
        analyzed = db.maintain_sqlite(statistics="analyze", checkpoint=None)
        assert analyzed["statistics"] == {"action": "analyze", "completed": True}
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT stat FROM sqlite_stat1 WHERE idx='sample_value'"
        ).fetchone() == ("3 1",)


def test_optimize_bounds_and_restores_pre_346_analysis_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 44, 6))
    with melddb.open(tmp_path / "old-optimize.db", journal_mode="delete") as db:
        db._backend.conn.execute("PRAGMA analysis_limit=123")
        statements = []
        db._backend.conn.set_trace_callback(statements.append)
        db.maintain_sqlite(checkpoint=None)
        assert "PRAGMA analysis_limit=400" in statements
        assert db._backend.conn.execute("PRAGMA analysis_limit").fetchone() == (123,)


def test_statistics_lock_failure_is_translated(tmp_path):
    path = tmp_path / "locked.db"
    with melddb.open(path, timeout=0, journal_mode="delete") as db:
        db.sql("CREATE TABLE sample(value)")
        with sqlite3.connect(path, timeout=0, autocommit=True) as blocker:
            blocker.execute("BEGIN EXCLUSIVE")
            try:
                with pytest.raises(BusyError):
                    db.maintain_sqlite(statistics="analyze", checkpoint=None)
            finally:
                blocker.execute("ROLLBACK")


@pytest.mark.parametrize("statistics", ["full", "ANALYZE", 1, False])
def test_invalid_statistics_selection_is_rejected(tmp_path, statistics):
    with melddb.open(tmp_path / "invalid-statistics.db", journal_mode="delete") as db:
        with pytest.raises(ValidationError, match="statistics"):
            db.maintain_sqlite(statistics=statistics, checkpoint=None)


def test_checkpoint_reports_no_wal(tmp_path):
    with melddb.open(tmp_path / "delete.db", journal_mode="delete") as db:
        result = db.maintain_sqlite(statistics=None)["checkpoint"]
        assert result == {
            "mode": "passive",
            "busy": False,
            "log_frames": None,
            "checkpointed_frames": None,
            "complete": False,
            "wal_active": False,
        }


@pytest.mark.parametrize("mode", ["full", "restart", "truncate"])
def test_blocking_checkpoint_modes_report_busy(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    path = tmp_path / f"{mode}.db"
    with melddb.open(path, timeout=0, journal_mode="wal") as db:
        db.sql("CREATE TABLE sample(value BLOB)")
        db.sql("INSERT INTO sample VALUES(zeroblob(20000))")
        db.maintain_sqlite(statistics=None, checkpoint="truncate")
        with sqlite3.connect(path, timeout=0, autocommit=True) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM sample").fetchall()
            for _ in range(3):
                db.sql("UPDATE sample SET value=randomblob(20000)")
            checkpoint = db.maintain_sqlite(statistics=None, checkpoint=mode)["checkpoint"]
            assert checkpoint["busy"] is True
            assert checkpoint["complete"] is False
            reader.execute("ROLLBACK")
        complete = db.maintain_sqlite(statistics=None, checkpoint="truncate")["checkpoint"]
        assert complete["busy"] is False
        assert complete["complete"] is True


def test_passive_checkpoint_reports_partial_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    path = tmp_path / "passive.db"
    with melddb.open(path, timeout=0, journal_mode="wal") as db:
        db.sql("CREATE TABLE sample(value BLOB)")
        db.sql("INSERT INTO sample VALUES(zeroblob(20000))")
        db.maintain_sqlite(statistics=None, checkpoint="truncate")
        with sqlite3.connect(path, timeout=0, autocommit=True) as reader:
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM sample").fetchall()
            for _ in range(3):
                db.sql("UPDATE sample SET value=randomblob(20000)")
            checkpoint = db.maintain_sqlite(statistics=None)["checkpoint"]
            assert checkpoint["busy"] is False
            assert checkpoint["log_frames"] > checkpoint["checkpointed_frames"]
            assert checkpoint["complete"] is False
            reader.execute("ROLLBACK")


@pytest.mark.parametrize("checkpoint", ["noop", "PASSIVE", 1, False])
def test_invalid_checkpoint_selection_is_rejected(tmp_path, checkpoint):
    with melddb.open(tmp_path / "invalid-checkpoint.db", journal_mode="delete") as db:
        with pytest.raises(ValidationError, match="checkpoint"):
            db.maintain_sqlite(statistics=None, checkpoint=checkpoint)


def test_maintenance_requires_an_action(tmp_path):
    with melddb.open(tmp_path / "no-action.db", journal_mode="delete") as db:
        with pytest.raises(ValidationError, match="at least one"):
            db.maintain_sqlite(statistics=None, checkpoint=None)


def test_maintenance_rejects_unsupported_handles(tmp_path):
    path = tmp_path / "readonly.db"
    with melddb.open(path, journal_mode="delete"):
        pass
    with melddb.open(path, readonly=True) as db:
        with pytest.raises(UnsupportedError, match="writable"):
            db.maintain_sqlite()
    with melddb.open(":memory:") as db:
        with pytest.raises(UnsupportedError, match="file-backed"):
            db.maintain_sqlite()
    with melddb.open(tmp_path / "postgres.db", journal_mode="delete") as db:
        db._backend.pg = True
        try:
            with pytest.raises(UnsupportedError, match="SQLite"):
                db.maintain_sqlite()
        finally:
            db._backend.pg = False


def test_maintenance_inside_transaction_poisoned_and_rolls_back(tmp_path):
    with melddb.open(tmp_path / "transaction.db", journal_mode="delete") as db:
        with pytest.raises(TransactionError, match="failed operation"):
            with db.transaction():
                with pytest.raises(OwnershipError, match="transaction-owned"):
                    db.maintain_sqlite()


def test_maintenance_is_thread_confined(tmp_path):
    with melddb.open(tmp_path / "thread.db", journal_mode="delete") as db:
        errors = []

        def maintain():
            try:
                db.maintain_sqlite()
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=maintain)
        thread.start()
        thread.join()
        assert len(errors) == 1
        assert "another thread" in str(errors[0])
