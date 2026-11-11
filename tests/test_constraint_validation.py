from concurrent.futures import ThreadPoolExecutor

import pytest

from melddb.errors import ConstraintError, OwnershipError, TransactionError, UnsupportedError


def setup(db):
    db.sql("CREATE TABLE app_parent(id INTEGER PRIMARY KEY)")
    db.sql("CREATE TABLE app_child(id INTEGER REFERENCES app_parent(id) DEFERRABLE INITIALLY DEFERRED)")


def test_validation_rollback_and_success(db):
    setup(db)
    with pytest.raises(RuntimeError):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_child VALUES(1)")
            tx.sql("INSERT INTO app_parent VALUES(1)")
            assert tx.validate_constraints() is None
            raise RuntimeError("intentional rollback")
    assert db.sql("SELECT * FROM app_child") == []
    with db.transaction() as tx:
        tx.sql("INSERT INTO app_parent VALUES(1)")
        tx.sql("INSERT INTO app_child VALUES(1)")
        tx.validate_constraints()
    assert db.sql("SELECT * FROM app_child") == [{"id": 1}]


def test_failed_check_poisons_even_when_caught(db):
    setup(db)
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_child VALUES(1)")
            with pytest.raises(ConstraintError):
                tx.validate_constraints()
            with pytest.raises(TransactionError):
                tx.validate_constraints()
    assert db.sql("SELECT * FROM app_child") == []


def test_validation_scope_checks(db):
    with pytest.raises(UnsupportedError):
        with db.transaction(write=False) as tx:
            tx.validate_constraints()
    with db.transaction() as expired:
        expired.validate_constraints()
    with pytest.raises(OwnershipError):
        expired.validate_constraints()
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            with ThreadPoolExecutor(1) as pool:
                with pytest.raises(OwnershipError):
                    pool.submit(tx.validate_constraints).result()


def test_postgres_deferred_unique_and_trigger(db):
    if not db._backend.pg:
        pytest.skip("PostgreSQL deferrable unique and constraint-trigger semantics")
    db.sql("CREATE TABLE app_unique(id INTEGER UNIQUE DEFERRABLE INITIALLY DEFERRED)")
    with pytest.raises(ConstraintError):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_unique VALUES(1),(1)")
            tx.validate_constraints()
    db.sql("CREATE FUNCTION app_reject() RETURNS trigger LANGUAGE plpgsql AS "
           "'BEGIN RAISE EXCEPTION USING ERRCODE=''23514'', MESSAGE=''rejected''; END'")
    db.sql("CREATE CONSTRAINT TRIGGER app_trigger AFTER INSERT ON app_unique "
           "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION app_reject()")
    with pytest.raises(ConstraintError):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_unique VALUES(2)")
            tx.validate_constraints()
    assert db.sql("SELECT * FROM app_unique") == []


def test_postgres_validation_leaves_checks_immediate(db):
    if not db._backend.pg:
        pytest.skip("PostgreSQL constraint timing")
    setup(db)
    with pytest.raises(ConstraintError):
        with db.transaction() as tx:
            tx.validate_constraints()
            tx.sql("INSERT INTO app_child VALUES(1)")


def test_postgres_deferred_exclusion(db):
    if not db._backend.pg:
        pytest.skip("PostgreSQL deferred exclusion constraints")
    db.sql("CREATE TABLE app_intervals(span int4range, "
           "EXCLUDE USING gist (span WITH &&) DEFERRABLE INITIALLY DEFERRED)")
    with pytest.raises(ConstraintError):
        with db.transaction() as tx:
            tx.sql("INSERT INTO app_intervals VALUES('[1,5)'),('[3,7)')")
            tx.validate_constraints()
    assert db.sql("SELECT * FROM app_intervals") == []
