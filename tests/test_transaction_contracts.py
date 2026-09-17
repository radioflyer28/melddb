"""Enforced read scopes and fail-closed transaction finalization."""
import os
import sqlite3
import uuid

import pytest

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import (
    BusyError,
    CommitError,
    RollbackError,
    TransactionError,
    TransactionOutcomeError,
    UnsupportedError,
    ValidationError,
)


def install_docs(db):
    db.migrate(Migration("001", (s.collection("docs"),)))


def test_managed_writes_are_rejected_and_poison_read_transaction(db):
    install_docs(db)
    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction(write=False) as tx:
            with pytest.raises(UnsupportedError, match="read-only"):
                tx.collection("docs").insert({"forbidden": True})
    assert db.collection("docs").find() == []


def test_readonly_database_rejects_writes_before_mutation(tmp_path):
    path = tmp_path / "readonly.db"
    with melddb.open(path, journal_mode="delete") as writable:
        install_docs(writable)
        writable.collection("docs").insert({"kept": True}, id="kept")

    with melddb.open(path, readonly=True) as readonly:
        with pytest.raises(UnsupportedError, match="read-only"):
            with readonly.transaction(write=True):
                pytest.fail("write transaction must not be yielded")
        with pytest.raises(UnsupportedError, match="read-only"):
            readonly.collection("docs").insert({"forbidden": True})
        assert readonly.collection("docs").get("kept")["body"] == {"kept": True}


@pytest.mark.skipif(not os.getenv("MELDDB_TEST_POSTGRES"), reason="PostgreSQL not configured")
def test_postgres_readonly_database_rejects_writes():
    import psycopg
    from psycopg.conninfo import make_conninfo

    namespace = "test_" + uuid.uuid4().hex
    admin = psycopg.connect(os.environ["MELDDB_TEST_POSTGRES"], autocommit=True)
    admin.execute(f'CREATE SCHEMA "{namespace}"')
    url = make_conninfo(
        os.environ["MELDDB_TEST_POSTGRES"], options=f"-c search_path={namespace}"
    )
    try:
        with melddb.connect(url) as writable:
            writable.sql("CREATE TABLE application_data(value INTEGER)")
            writable.sql("INSERT INTO application_data VALUES(1)")
        with melddb.connect(url, readonly=True) as readonly:
            assert readonly.sql("SELECT * FROM application_data", write=False) == [
                {"value": 1}
            ]
            with pytest.raises(UnsupportedError, match="read-only"):
                with readonly.transaction(write=True):
                    pytest.fail("write transaction must not be yielded")
    finally:
        try:
            admin.execute(f'DROP SCHEMA "{namespace}" CASCADE')
        finally:
            admin.close()


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO application_data VALUES(2)",
        "WITH source(value) AS (SELECT 2) INSERT INTO application_data SELECT value FROM source",
    ],
)
def test_raw_sql_mutations_are_backend_rejected_in_read_transaction(db, statement):
    db.sql("CREATE TABLE application_data(value INTEGER)")
    db.sql("INSERT INTO application_data VALUES(1)")
    with pytest.raises(ValidationError):
        with db.transaction(write=False) as tx:
            tx.sql(statement)
    assert db.sql("SELECT value FROM application_data", write=False) == [{"value": 1}]


def test_trigger_mediated_sql_mutation_is_rejected_without_classification(db):
    if db._backend.pg:
        pytest.skip("SQLite trigger syntax; PostgreSQL mutation coverage runs above")
    db.sql("CREATE TABLE application_data(value INTEGER)")
    db.sql("CREATE VIEW application_view AS SELECT value FROM application_data")
    db.sql(
        "CREATE TRIGGER application_insert INSTEAD OF INSERT ON application_view "
        "BEGIN INSERT INTO application_data VALUES(NEW.value); END"
    )
    with pytest.raises(ValidationError):
        with db.transaction(write=False) as tx:
            tx.sql("INSERT INTO application_view VALUES(1)")
    assert db.sql("SELECT * FROM application_data", write=False) == []


def test_standalone_sql_intent_and_transaction_mode_inheritance(db):
    db.sql("CREATE TABLE application_data(value INTEGER)")
    db.sql("INSERT INTO application_data VALUES(1)")
    assert db.sql("SELECT value FROM application_data", write=False) == [{"value": 1}]
    with pytest.raises(ValidationError, match="write must be boolean"):
        db.sql("SELECT 1", write=1)
    with pytest.raises(ValidationError, match="write must be boolean"):
        with db.transaction(write="no"):
            pass
    with db.transaction(write=False) as tx:
        assert tx.sql("SELECT value FROM application_data") == [{"value": 1}]
        with pytest.raises(TypeError):
            tx.sql("SELECT 1", write=False)


def test_wal_reader_does_not_reserve_writer_and_keeps_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 51, 3))
    path = tmp_path / "concurrent.db"
    with melddb.open(path, journal_mode="wal", timeout=0) as reader:
        reader.sql("CREATE TABLE application_data(value INTEGER)")
        reader.sql("INSERT INTO application_data VALUES(1)")
        with melddb.open(path, journal_mode="wal", timeout=0) as writer:
            with reader.transaction(write=False) as tx:
                assert tx.sql("SELECT value FROM application_data") == [{"value": 1}]
                writer.sql("UPDATE application_data SET value=2")
                assert tx.sql("SELECT value FROM application_data") == [{"value": 1}]
            assert reader.sql("SELECT value FROM application_data", write=False) == [
                {"value": 2}
            ]


def test_expected_busy_begin_leaves_handle_reusable(tmp_path):
    path = tmp_path / "busy.db"
    with melddb.open(path, journal_mode="delete", timeout=0) as holder:
        holder.sql("CREATE TABLE application_data(value INTEGER)")
        with melddb.open(path, journal_mode="delete", timeout=0) as contender:
            with holder.transaction():
                with pytest.raises(BusyError):
                    with contender.transaction():
                        pass
            assert contender.sql("SELECT * FROM application_data", write=False) == []


def test_uncertain_begin_quarantines_handle(tmp_path, monkeypatch):
    db = melddb.open(tmp_path / "uncertain-begin.db", journal_mode="delete")
    original_begin = db._backend.begin
    marker = RuntimeError("begin acknowledgement lost")
    cleanup = RuntimeError("begin recovery failed")

    def uncertain_begin(write=True):
        original_begin(write)
        raise marker

    monkeypatch.setattr(db._backend, "begin", uncertain_begin)
    monkeypatch.setattr(db._backend, "rollback", lambda: (_ for _ in ()).throw(cleanup))
    with pytest.raises(TransactionOutcomeError) as caught:
        with db.transaction():
            pass
    assert caught.value.phase == "begin"
    assert caught.value.outcome == "unknown"
    assert caught.value.initiating_error is marker
    assert caught.value.backend_error is cleanup
    with pytest.raises(TransactionError, match="close and reopen"):
        db.inspect()
    db.close()


def test_deferred_commit_failure_is_uncertain_and_requires_reopen(tmp_path):
    path = tmp_path / "deferred.db"
    db = melddb.open(path, journal_mode="delete")
    db.sql("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
    db.sql(
        "CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    with pytest.raises(CommitError) as caught:
        with db.transaction() as tx:
            tx.sql("INSERT INTO child VALUES(1)")
    assert caught.value.phase == "commit"
    assert caught.value.outcome == "unknown"
    assert caught.value.__cause__ is caught.value.backend_error
    with pytest.raises(TransactionError, match="close and reopen"):
        db.sql("SELECT * FROM child", write=False)
    db.close()
    with melddb.open(path, journal_mode="delete") as reopened:
        assert reopened.sql("SELECT * FROM child", write=False) == []


@pytest.mark.parametrize("durable", [False, True])
def test_lost_commit_acknowledgement_is_never_retried(tmp_path, monkeypatch, durable):
    path = tmp_path / f"commit-{durable}.db"
    db = melddb.open(path, journal_mode="delete")
    db.sql("CREATE TABLE application_data(value INTEGER)")
    original_commit = db._backend.commit
    marker = RuntimeError("commit acknowledgement lost")

    def uncertain_commit():
        if durable:
            original_commit()
        raise marker

    monkeypatch.setattr(db._backend, "commit", uncertain_commit)
    with pytest.raises(CommitError) as caught:
        with db.transaction() as tx:
            tx.sql("INSERT INTO application_data VALUES(1)")
    assert caught.value.backend_error is marker
    assert caught.value.__cause__ is marker
    with pytest.raises(TransactionError, match="close and reopen"):
        db.inspect()
    db.close()
    with melddb.open(path, journal_mode="delete") as reopened:
        rows = reopened.sql("SELECT * FROM application_data", write=False)
        assert rows == ([{"value": 1}] if durable else [])


def test_successful_rollback_preserves_initiating_exception(tmp_path):
    marker = RuntimeError("application failed")
    with melddb.open(tmp_path / "rollback.db", journal_mode="delete") as db:
        with pytest.raises(RuntimeError) as caught:
            with db.transaction():
                raise marker
        assert caught.value is marker
        assert db.sql("SELECT 1 AS value", write=False) == [{"value": 1}]


def test_rollback_failure_retains_both_errors_and_quarantines(tmp_path, monkeypatch):
    db = melddb.open(tmp_path / "rollback-failure.db", journal_mode="delete")
    marker = RuntimeError("application failed")
    cleanup = RuntimeError("rollback failed")
    monkeypatch.setattr(db._backend, "rollback", lambda: (_ for _ in ()).throw(cleanup))
    with pytest.raises(RollbackError) as caught:
        with db.transaction():
            raise marker
    assert caught.value.phase == "rollback"
    assert caught.value.outcome == "unknown"
    assert caught.value.initiating_error is marker
    assert caught.value.backend_error is cleanup
    assert caught.value.__cause__ is marker
    with pytest.raises(TransactionError, match="close and reopen"):
        db.check()
    db.close()


@pytest.mark.parametrize("committed", [False, True])
def test_read_mode_cleanup_failure_reports_known_outcome(
    tmp_path, monkeypatch, committed
):
    db = melddb.open(tmp_path / f"cleanup-{committed}.db", journal_mode="delete")
    cleanup = RuntimeError("query-only restoration failed")
    marker = RuntimeError("application failed")
    monkeypatch.setattr(
        db._backend,
        "finish_transaction",
        lambda: (_ for _ in ()).throw(cleanup),
    )
    error = CommitError if committed else RollbackError
    with pytest.raises(error) as caught:
        with db.transaction(write=False):
            if not committed:
                raise marker
    assert caught.value.phase == "cleanup"
    assert caught.value.outcome == ("committed" if committed else "rolled_back")
    assert caught.value.backend_error is cleanup
    assert caught.value.initiating_error is (None if committed else marker)
    with pytest.raises(TransactionError, match="close and reopen"):
        db.inspect()
    db.close()


def quarantine(db, monkeypatch):
    marker = RuntimeError("commit result unavailable")
    monkeypatch.setattr(db._backend, "commit", lambda: (_ for _ in ()).throw(marker))
    with pytest.raises(CommitError):
        with db.transaction():
            pass


@pytest.mark.parametrize(
    "operation",
    [
        lambda db, tmp: db.sql("SELECT 1", write=False),
        lambda db, tmp: db.collection("missing").get("id"),
        lambda db, tmp: db.transaction().__enter__(),
        lambda db, tmp: db.maintain_sqlite(checkpoint=None),
        lambda db, tmp: db.sqlite_runtime(),
        lambda db, tmp: db.inspect(),
        lambda db, tmp: db.check(),
        lambda db, tmp: db.backup(tmp / "backup.db"),
        lambda db, tmp: db.export(tmp / "export.json"),
        lambda db, tmp: db.import_into(tmp / "missing.json"),
    ],
)
def test_quarantine_rejects_public_operations_without_io(
    tmp_path, monkeypatch, operation
):
    db = melddb.open(tmp_path / "quarantine.db", journal_mode="delete")
    quarantine(db, monkeypatch)
    monkeypatch.setattr(
        db._backend,
        "execute",
        lambda *args, **kwargs: pytest.fail("quarantined operation performed database I/O"),
    )
    with pytest.raises(TransactionError, match="close and reopen"):
        operation(db, tmp_path)
    db.close()
    db.close()
