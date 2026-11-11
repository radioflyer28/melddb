"""Regression coverage for the provider boundary used by application catalogs."""

import pytest

from melddb.backend import Backend
from melddb.errors import (
    AlreadyExistsError,
    BusyError,
    ConnectionError,
    ConstraintError,
    TransactionError,
    UnsupportedError,
    ValidationError,
)


@pytest.mark.parametrize("statement", [
    "COMMIT;", "END;", "ROLLBACK;", "; ; /* prefix */ cOmMiT;",
    "-- prefix\nCOMMIT;", "/* prefix */BEGIN;", "SAVEPOINT\"point\"",
    "RELEASE\"point\"", "\ufeffCOMMIT;",
])
@pytest.mark.parametrize("bulk", [False, True])
def test_controls_reject_before_execution_and_bulk_consumption(db, statement, bulk):
    db.sql("CREATE TABLE app_guard(id INTEGER PRIMARY KEY)")
    consumed = []

    def parameters():
        consumed.append(True)
        yield ()

    with pytest.raises(TransactionError, match="failed operation"):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_guard VALUES (1)")
            with pytest.raises(UnsupportedError):
                if bulk:
                    tx.sql_many(statement, parameters())
                else:
                    tx.sql(statement)
            with pytest.raises(TransactionError):
                tx.sql("SELECT 1")
    assert consumed == []
    assert db.sql("SELECT * FROM app_guard", write=False) == []


@pytest.mark.parametrize("bulk", [False, True])
def test_comment_nesting_follows_selected_backend(db, bulk):
    statement = ("/* outer /* inner */ still commented */COMMIT;" if db._backend.pg
                 else "/* outer /* inner */COMMIT; -- */")
    with pytest.raises(UnsupportedError):
        with db.transaction() as tx:
            if bulk:
                tx.sql_many(statement, [()])
            else:
                tx.sql(statement)


def test_line_comment_ending_follows_selected_backend(db):
    if db._backend.pg:
        with pytest.raises(UnsupportedError):
            db.sql("-- prefix\rCOMMIT;")
    else:
        assert db.sql("-- prefix\rCOMMIT;\nSELECT 1 AS value", write=False) == [{"value": 1}]


@pytest.mark.parametrize("statement", ["/* not closed", None, b"COMMIT;"])
def test_invalid_statement_poisoning(db, statement):
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            with pytest.raises(ValidationError):
                tx.sql(statement)


def test_literals_identifiers_and_bound_values_are_not_rewritten(db):
    db.sql('CREATE TABLE "COMMIT; -- /* table */"("END;" TEXT)')
    marker = "%s" if db._backend.pg else "?"
    value = "COMMIT; -- /* 'quoted' */ ? %"
    with db.transaction() as tx:
        tx.sql(f'INSERT INTO "COMMIT; -- /* table */" VALUES ({marker})', (value,))
        assert tx.sql("SELECT 'COMMIT; -- /* body */' AS text") == [
            {"text": "COMMIT; -- /* body */"}
        ]
    assert db.sql('SELECT "END;" AS value FROM "COMMIT; -- /* table */"', write=False) == [
        {"value": value}
    ]


def test_application_routine_bodies_remain_native(db):
    db.sql("CREATE TABLE app_guard(id INTEGER PRIMARY KEY)")
    if db._backend.pg:
        db.sql("CREATE FUNCTION app_literal() RETURNS text LANGUAGE SQL AS "
               "$$ SELECT 'COMMIT; /* body */' $$")
        assert db.sql("SELECT app_literal() AS value", write=False) == [
            {"value": "COMMIT; /* body */"}
        ]
    else:
        db.sql("CREATE TABLE app_audit(value TEXT)")
        db.sql("CREATE TRIGGER app_record AFTER INSERT ON app_guard BEGIN "
               "INSERT INTO app_audit VALUES ('COMMIT; /* body */'); "
               "INSERT INTO app_audit VALUES ('END;'); END")
        db.sql("INSERT INTO app_guard VALUES (1)")
        assert db.sql("SELECT value FROM app_audit ORDER BY rowid", write=False) == [
            {"value": "COMMIT; /* body */"}, {"value": "END;"}
        ]


@pytest.mark.parametrize("statement", [
    "ABORT;", "START TRANSACTION", "SET TRANSACTION READ WRITE", "RESET ALL",
    "DISCARD ALL", "PREPARE x AS SELECT 1", "PREPARE TRANSACTION 'x'",
    "EXECUTE x", "DEALLOCATE ALL",
])
@pytest.mark.parametrize("bulk", [False, True])
def test_postgres_session_controls_rejected(db, statement, bulk):
    if not db._backend.pg:
        pytest.skip("PostgreSQL-specific session syntax")
    with pytest.raises(UnsupportedError):
        with db.transaction() as tx:
            if bulk:
                tx.sql_many(statement, [()])
            else:
                tx.sql(statement)


def test_postgres_function_cannot_upgrade_read_scope(db):
    if not db._backend.pg:
        pytest.skip("PostgreSQL-specific configuration function")
    with pytest.raises(ValidationError):
        with db.transaction(write=False) as tx:
            tx.sql("SELECT set_config('transaction_read_only', 'off', true)")


@pytest.mark.parametrize("code, expected", [
    ("08006", ConnectionError), ("57P01", ConnectionError), ("57P02", ConnectionError),
    ("57P03", ConnectionError), ("57P04", ConnectionError), ("57P05", ConnectionError),
    ("25P03", ConnectionError), ("55P03", BusyError), ("40001", BusyError),
    ("40P01", BusyError), ("23505", AlreadyExistsError), ("23503", ConstraintError),
    ("57014", ValidationError), ("42601", ValidationError),
])
def test_postgres_error_classification_retains_driver_cause(code, expected):
    psycopg = pytest.importorskip("psycopg")
    backend = Backend.__new__(Backend)
    backend.pg = True
    driver_error = psycopg.errors.lookup(code)("synthetic driver error")
    with pytest.raises(expected) as caught:
        backend._raise_translated(driver_error)
    assert caught.value.__cause__ is driver_error


@pytest.mark.parametrize("kind", ["OperationalError", "InterfaceError"])
def test_postgres_driver_disconnect_without_sqlstate(kind):
    psycopg = pytest.importorskip("psycopg")
    backend = Backend.__new__(Backend)
    backend.pg = True
    driver_error = getattr(psycopg, kind)("connection closed")
    assert driver_error.sqlstate is None
    with pytest.raises(ConnectionError) as caught:
        backend._raise_translated(driver_error)
    assert caught.value.__cause__ is driver_error
