"""S08 migration atomicity and SQL-enforced evolution on existing data."""
import json
import sqlite3

import pytest

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import MigrationError, UnsupportedError, ValidationError


@pytest.mark.parametrize("operation", [None, {}, {"op": []}, {"op": "drop", "name": "x"},
    {"op": "collection", "name": "x", "typo": True}, s.table("x", {"ID": "text"}),
    s.table("x", {"a": "text", "A": "text"}), s.table("x", {"a": []}),
    s.index("x", "v", unique="yes"), s.require("x"), s.type_of("x", "v", type=[]),
    s.relationship("x", "a", "b", properties=1)])
def test_preflight_before_ddl(db, monkeypatch, operation):
    original = db._backend.execute
    mutations = []
    def tracked(statement, *args, **kwargs):
        if statement.startswith(("CREATE", "INSERT", "UPDATE")):
            mutations.append(statement)
        return original(statement, *args, **kwargs)
    monkeypatch.setattr(db._backend, "execute", tracked)
    with pytest.raises(ValidationError):
        db.migrate(Migration("001", (s.collection("valid"),)), Migration("002", (operation,)))
    assert mutations == []
    assert db.inspect()["objects"] == []


def test_order_checksum_and_request_rollback(db):
    first = Migration("001", (s.collection("docs"),))
    db.migrate(first)
    db.migrate(first)
    before = db.inspect()
    for revisions in [(Migration("000", (s.collection("early"),)),),
                      (Migration("002", (s.collection("new"),)), Migration("001", (s.collection("drift"),)))]:
        with pytest.raises(MigrationError):
            db.migrate(*revisions)
        assert db.inspect() == before
    db.migrate(Migration("002", (s.collection("new"),)))


@pytest.fixture
def sqlite_db(tmp_path):
    with melddb.open(tmp_path / "evolution.db") as db:
        yield db


def physical(db, name):
    return next(o["physical"] for o in db.inspect()["objects"] if o["name"] == name)


def test_invalid_existing_data_leaves_entire_request_unchanged(sqlite_db):
    db = sqlite_db
    docs = db.collection("docs")
    docs.insert({"key": "duplicate"}, id="a")
    docs.insert({"key": "duplicate"}, id="b")
    before = db.inspect()
    schema_before = db.sql("SELECT name,sql FROM sqlite_schema ORDER BY name")
    with pytest.raises(ValidationError) as caught:
        db.migrate(Migration("001", (s.table("new", {"n": "integer"}), s.require("docs", "key"),
                                     s.index("docs", "key", unique=True))))
    assert caught.value.violations == [
        {"storage": "docs", "path": ["key"], "rule": "index", "id": i, "count": 2} for i in "ab"]
    assert db.inspect() == before
    assert db.sql("SELECT name,sql FROM sqlite_schema ORDER BY name") == schema_before
    assert len(docs.find()) == 2
    docs.replace("b", {"key": "different"})
    db.migrate(Migration("001", (s.require("docs", "key"), s.index("docs", "key", unique=True))))


@pytest.mark.parametrize("kind,valid,invalid", [("string", "x", 1), ("number", 1.5, True),
                                              ("integer", 1, 1.5), ("boolean", False, 0)])
def test_primitive_rules_enforced_without_sdk(sqlite_db, kind, valid, invalid):
    db = sqlite_db
    db.collection("docs").insert({}, id="old")
    db.migrate(Migration("001", (s.type_of("docs", "nested", 'odd"key', type=kind),)))
    name = physical(db, "docs")
    with sqlite3.connect(db._backend.path, autocommit=True) as connection:
        for i, body in enumerate([{}, {"nested": {'odd"key': None}}, {"nested": {'odd"key': valid}}]):
            connection.execute(f'INSERT INTO "{name}" VALUES (?,1,?)', (str(i), json.dumps(body)))
        for sql, params in [
            (f'INSERT INTO "{name}" VALUES (?,1,?)', ("bad", json.dumps({"nested": {'odd"key': invalid}}))),
            (f'UPDATE "{name}" SET body=? WHERE id=?', (json.dumps({"nested": {'odd"key': invalid}}), "old")),
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql, params)
    assert db.check()["ok"]


def test_required_and_unique_sql_semantics(sqlite_db):
    db = sqlite_db
    db.migrate(Migration("001", (s.collection("docs"), s.table("people", {"email": "text"}))))
    db.migrate(Migration("002", (s.index("docs", "v", unique=True), s.require("people", "email"),
                                 s.index("people", "email", unique=True))))
    doc, table = physical(db, "docs"), physical(db, "people")
    with sqlite3.connect(db._backend.path, autocommit=True) as connection:
        for i, body in enumerate([{}, {}, {"v": None}, {"v": None}, {"v": False}, {"v": 0},
                                  {"v": True}, {"v": 1}, {"v": "1"}, {"v": "A"}, {"v": "a"}]):
            connection.execute(f'INSERT INTO "{doc}" VALUES (?,1,?)', (str(i), json.dumps(body)))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f'INSERT INTO "{doc}" VALUES (?,1,?)', ("duplicate", '{"v":1.0}'))
        connection.execute(f'INSERT INTO "{table}" VALUES (?,?)', ("person", "a@example.test"))
        for values in [("missing", None), ("duplicate", "a@example.test")]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f'INSERT INTO "{table}" VALUES (?,?)', values)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(f'UPDATE "{table}" SET email=NULL')
    assert db.check()["ok"]


def test_required_path_missing_null_arrays_and_idempotent_rules(sqlite_db):
    db = sqlite_db
    docs = db.collection("docs")
    for ident, body in [("missing", {}), ("null", {"a": {"0": None}}), ("array", {"a": [1]})]:
        docs.insert(body, id=ident)
    rule = s.require("docs", "a", "0")
    with pytest.raises(ValidationError) as caught:
        db.migrate(Migration("001", (rule,)))
    assert [v["id"] for v in caught.value.violations] == ["array", "missing", "null"]
    for row in docs.find():
        docs.replace(row["id"], {"a": {"0": row["id"]}})
    db.migrate(Migration("001", (rule, rule)), Migration("002", (rule,)))
    assert db.inspect()["objects"][0]["schema"]["constraints"] == [rule]
    assert len(db.inspect()["migrations"]) == 2


def test_postgres_evolution_preflight_across_revisions(db, monkeypatch):
    if not db._backend.pg:
        return
    original = db._backend.execute
    mutations = []
    def tracked(statement, *args, **kwargs):
        if statement.startswith(("CREATE", "INSERT", "UPDATE")):
            mutations.append(statement)
        return original(statement, *args, **kwargs)
    monkeypatch.setattr(db._backend, "execute", tracked)
    with pytest.raises(UnsupportedError):
        db.migrate(Migration("001", (s.collection("docs"),)), Migration("002", (s.require("docs", "v"),)))
    assert not mutations


def test_metadata_version_refuses_open(tmp_path):
    path = tmp_path / "format.db"
    with melddb.open(path) as db:
        db.collection("docs").insert({})
    with sqlite3.connect(path, autocommit=True) as connection:
        connection.execute("UPDATE _melddb_format SET version=999")
    with pytest.raises(MigrationError):
        melddb.open(path)


def test_violation_limit_reports_full_group_size(sqlite_db):
    db = sqlite_db
    with db.transaction() as tx:
        for i in range(105):
            tx.collection("docs").insert({"key": "same"}, id=f"{i:03}")
    with pytest.raises(ValidationError) as caught:
        db.migrate(Migration("001", (s.index("docs", "key", unique=True),)))
    assert len(caught.value.violations) == 100
    assert caught.value.violations[-1]["id"] == "099"
    assert all(v["count"] == 105 for v in caught.value.violations)
    assert db.inspect()["migrations"] == []


def test_binary_revision_order_and_invalid_revision_shapes(db):
    for revision in [None, Migration("", ()), Migration("001", None)]:
        with pytest.raises(ValidationError):
            db.migrate(revision)
        assert not db.inspect()["objects"]
    db.migrate(Migration("Z", (s.collection("docs"),)), Migration("a", ()))
    with pytest.raises(MigrationError):
        db.migrate(Migration("_", ()))
    assert {m["id"] for m in db.inspect()["migrations"]} == {"Z", "a"}
