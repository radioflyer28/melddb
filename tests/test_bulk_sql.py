"""Transaction-scoped bulk SQL conformance."""
import threading

import pytest

from melddb import Migration
from melddb import schema as s
from melddb.errors import (
    ConstraintError,
    OwnershipError,
    TransactionError,
    UnsupportedError,
    ValidationError,
)


def parameter(db):
    return "%s" if db.inspect()["backend"] == "postgresql" else "?"


def install_schema(db):
    db.sql("CREATE TABLE app_parent(id TEXT PRIMARY KEY)")
    db.sql(
        "CREATE TABLE app_event("
        "position INTEGER PRIMARY KEY, parent_id TEXT NOT NULL REFERENCES app_parent(id))"
    )


def test_bulk_sql_composes_with_managed_and_application_work(db):
    install_schema(db)
    db.migrate(Migration("001", (s.collection("docs"),)))
    marker = parameter(db)

    with db.transaction() as tx:
        tx.collection("docs").insert({"state": "ready"}, id="doc-1")
        tx.sql(f"INSERT INTO app_parent VALUES ({marker})", ("parent-1",))
        result = tx.sql_many(
            f"INSERT INTO app_event VALUES ({marker},{marker})",
            ((position, "parent-1") for position in range(5)),
        )

    assert result == {"parameter_sets": 5, "affected_rows": 5}
    assert db.collection("docs").get("doc-1")["body"] == {"state": "ready"}
    assert db.sql("SELECT position FROM app_event ORDER BY position", write=False) == [
        {"position": position} for position in range(5)
    ]


def test_bulk_sql_empty_input_does_not_execute_or_consume(db, monkeypatch):
    calls = []
    original = db._backend.execute_many

    def recording_execute_many(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(db._backend, "execute_many", recording_execute_many)
    with db.transaction() as tx:
        assert tx.sql_many("this is intentionally invalid", iter(())) == {
            "parameter_sets": 0,
            "affected_rows": 0,
        }
    assert calls == []


def test_bulk_sql_consumes_generator_once_in_order(db):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    yielded = []

    def parameters():
        for position in range(1000):
            yielded.append(position)
            yield (position,)

    source = parameters()
    with db.transaction() as tx:
        result = tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", source)

    assert result == {"parameter_sets": 1000, "affected_rows": 1000}
    assert yielded == list(range(1000))
    assert list(source) == []
    assert db.sql("SELECT position FROM app_event ORDER BY position", write=False) == [
        {"position": position} for position in range(1000)
    ]


def test_bulk_sql_normalizes_unknown_affected_rows(db, monkeypatch):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    original = db._backend.execute_many

    def execute_without_rowcount(*args, **kwargs):
        original(*args, **kwargs)
        return None

    monkeypatch.setattr(db._backend, "execute_many", execute_without_rowcount)
    with db.transaction() as tx:
        result = tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", [(1,)])
    assert result == {"parameter_sets": 1, "affected_rows": None}


def test_bulk_sql_is_only_available_on_live_transaction_handle(db):
    assert not hasattr(db, "sql_many")
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction() as tx:
            assert tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", [(1,)]) == {
                "parameter_sets": 1,
                "affected_rows": 1,
            }
            with pytest.raises(OwnershipError, match="transaction-owned"):
                db.sql("SELECT 1", write=False)
    with pytest.raises(OwnershipError, match="expired"):
        tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", [(2,)])
    assert db.sql("SELECT * FROM app_event", write=False) == []


def test_bulk_sql_wrong_thread_is_rejected(db):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    errors = []
    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction() as tx:
            thread = threading.Thread(
                target=lambda: _capture(
                    errors,
                    lambda: tx.sql_many(
                        f"INSERT INTO app_event VALUES ({marker})", [(1,)]
                    ),
                )
            )
            thread.start()
            thread.join()
    assert len(errors) == 1
    assert isinstance(errors[0], OwnershipError)
    assert db.sql("SELECT * FROM app_event", write=False) == []


def _capture(errors, operation):
    try:
        operation()
    except Exception as exc:
        errors.append(exc)


def test_bulk_sql_read_transaction_rejects_before_iteration(db):
    consumed = False

    def parameters():
        nonlocal consumed
        consumed = True
        yield (1,)

    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction(write=False) as tx:
            with pytest.raises(UnsupportedError, match="read-only"):
                tx.sql_many("INSERT INTO app_event VALUES (?)", parameters())
    assert consumed is False


@pytest.mark.parametrize("statement", ["BEGIN", "-- comment\nCOMMIT", "PRAGMA foreign_keys=OFF"])
def test_bulk_sql_rejects_transaction_control_before_iteration(db, statement):
    consumed = False

    def parameters():
        nonlocal consumed
        consumed = True
        yield ()

    with pytest.raises(UnsupportedError, match="transaction/configuration"):
        with db.transaction() as tx:
            tx.sql_many(statement, parameters())
    assert consumed is False


def test_bulk_sql_constraint_failure_rolls_back_everything(db):
    install_schema(db)
    db.migrate(Migration("001", (s.collection("docs"),)))
    marker = parameter(db)

    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction() as tx:
            tx.collection("docs").insert({"state": "rollback"}, id="doc-1")
            tx.sql(f"INSERT INTO app_parent VALUES ({marker})", ("parent-1",))
            with pytest.raises(ConstraintError):
                tx.sql_many(
                    f"INSERT INTO app_event VALUES ({marker},{marker})",
                    [(1, "parent-1"), (2, "missing")],
                )
            with pytest.raises(TransactionError, match="failed"):
                tx.sql("SELECT 1")

    assert db.collection("docs").find() == []
    assert db.sql("SELECT * FROM app_parent", write=False) == []
    assert db.sql("SELECT * FROM app_event", write=False) == []


def test_bulk_sql_iteration_failure_rolls_back_partial_driver_work(db):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)

    def parameters():
        yield (1,)
        yield (2,)
        raise RuntimeError("parameter source failed")

    with pytest.raises(RuntimeError, match="parameter source failed"):
        with db.transaction() as tx:
            tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", parameters())
    assert db.sql("SELECT * FROM app_event", write=False) == []


def test_bulk_sql_binding_failure_is_translated_and_rolls_back(db):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    with pytest.raises(ValidationError):
        with db.transaction() as tx:
            tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", [(1,), ()])
    assert db.sql("SELECT * FROM app_event", write=False) == []


def test_bulk_sql_driver_failure_is_translated_and_rolls_back(db):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    with pytest.raises(ValidationError):
        with db.transaction() as tx:
            tx.sql_many(f"INSERT INTO app_event VALUES ({marker})", [(1,)])
            tx.sql_many(f"INSERT INTO missing_table VALUES ({marker})", [(2,)])
    assert db.sql("SELECT * FROM app_event", write=False) == []


@pytest.mark.parametrize("kind", ["select", "returning"])
def test_bulk_sql_rejects_result_producing_statements(db, kind):
    db.sql("CREATE TABLE app_event(position INTEGER PRIMARY KEY)")
    marker = parameter(db)
    statement = (
        f"SELECT {marker} AS position"
        if kind == "select"
        else f"INSERT INTO app_event VALUES ({marker}) RETURNING position"
    )
    with pytest.raises((UnsupportedError, ValidationError)):
        with db.transaction() as tx:
            tx.sql_many(statement, [(1,), (2,)])
    assert db.sql("SELECT * FROM app_event", write=False) == []
