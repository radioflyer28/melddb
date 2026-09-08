import json
import sqlite3
import threading
from pathlib import Path

import pytest

import melddb
from melddb import Migration, field
from melddb import schema as s
from melddb.errors import (
    AlreadyExistsError,
    ConflictError,
    ConstraintError,
    MigrationError,
    OwnershipError,
    TransactionError,
    TraversalLimitError,
    UnsupportedError,
    ValidationError,
)


def setup(db, cascade=False):
    db.migrate(Migration("001", (s.collection("docs"), s.table("rows", {"name": "text", "n": "integer"}),
                                s.relationship("links", "docs", "docs",
                                               on_delete="cascade" if cascade else "restrict"))))


def test_handles_and_detached_values(db):
    handle = db.collection("settings")
    assert db.inspect()["objects"] == []
    row = handle.insert({"nested": {"ok": True}})
    row["body"]["nested"]["ok"] = False
    assert handle.get(row["id"])["body"]["nested"]["ok"] is True
    assert handle.get("absent") is None
    assert handle.replace(row["id"], {"x": 1}, expected_version=1)["version"] == 2
    with pytest.raises(ConflictError):
        handle.replace(row["id"], {}, expected_version=1)
    assert handle.delete(row["id"], expected_version=2)


@pytest.mark.parametrize("failure", [1, 2, 3, None])
def test_mixed_rollback(db, failure):
    setup(db)
    target = db.collection("docs").insert({"target": True})
    def run():
        with db.transaction() as tx:
            a = tx.collection("docs").insert({"new": True})
            if failure == 1:
                raise RuntimeError("injected")
            tx.relationship("links").connect(tx.collection("docs").ref(a),
                                               tx.collection("docs").ref(target))
            if failure == 2:
                raise RuntimeError("injected")
            tx.table("rows").insert({"name": "created", "n": 1})
            if failure == 3:
                raise RuntimeError("injected")
    if failure:
        with pytest.raises(RuntimeError):
            run()
    else:
        run()
    assert len(db.collection("docs").find()) == (1 if failure else 2)
    assert len(db.table("rows").find()) == (0 if failure else 1)
    assert len(db.relationship("links").edges(
        db.collection("docs").ref(target), direction="in"
    )) == (0 if failure else 1)


def test_caught_errors_poison_transaction(db):
    setup(db)
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            tx.collection("docs").insert({})
            try:
                tx.table("rows").insert({"unknown": 2})
            except ValidationError:
                pass
    assert not db.collection("docs").find()
    with pytest.raises(OwnershipError):
        tx.collection("docs").get("id")
    with pytest.raises(TransactionError):
        with db.transaction():
            with pytest.raises(OwnershipError):
                db.collection("docs").get("id")


def test_thread_confinement(db):
    errors = []
    def run():
        try:
            db.collection("x").insert({})
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert isinstance(errors[0], OwnershipError)


def test_predicates(db):
    c = db.collection("docs")
    for ident, body in [("a", {}), ("b", {"v": None}), ("c", {"v": False}),
                        ("d", {"v": 0}), ("e", {"v": 1.5}), ("f", {"v": "1.5"})]:
        c.insert(body, id=ident)
    def ids(predicate):
        return [record["id"] for record in c.find(predicate)]

    assert ids(field("v").is_missing()) == ["a"]
    assert ids(field("v").is_null()) == ["b"]
    assert ids(field("v").eq(False)) == ["c"]
    assert ids(field("v").eq(0)) == ["d"]
    assert ids(field("v").gte(1)) == ["e"]
    assert ids(field("v").isin([0, "1.5"])) == ["d", "f"]
    assert ids(field("v").gte(0) & field("v").lt(1)) == ["d"]
    assert ids(field("v").eq(None)) == []
    assert [r["id"] for r in c.find(order_by=field("v"))] == list("abcdef")


@pytest.mark.parametrize("key", ['a.b', 'a"b', "a'b", 'a?%b', '雪', '', '0'])
def test_unusual_paths_and_names(db, key):
    c = db.collection("docs'\"?%" + key)
    c.insert({key: {"x": "'); DROP TABLE docs; --"}}, id="a")
    assert c.find(field(key, "x").eq("'); DROP TABLE docs; --"))[0]["id"] == "a"


@pytest.mark.parametrize("body", [{"v": float("nan")}, {"v": float("inf")}, {"v": 2**53},
                                  {"v": "\x00"}, {"v": "\ud800"}, {1: "x"}, []])
def test_invalid_json(db, body):
    with pytest.raises(ValidationError):
        db.collection("docs").insert(body)
    assert db.inspect()["objects"] == []


def test_types_projection_sql(db):
    db.migrate(Migration("001", (s.table("t", {"s": "text", "n": "integer", "f": "float",
                                               "b": "boolean", "blob": "bytes"}),)))
    t = db.table("t")
    row = t.insert({"s": "ok", "n": 2**63-1, "f": 1.5, "b": True, "blob": b"\x00\xff"})
    assert t.get(row["id"])["blob"] == b"\x00\xff"
    assert t.find(columns=["b"])[0] == {"b": True}
    with pytest.raises(ValidationError):
        t.update(row["id"], {"n": True})
    assert db.sql("WITH q AS (SELECT 7 AS x) SELECT x FROM q") == [{"x": 7}]
    assert t.update(row["id"], {"s": "new"})["s"] == "new"


def test_links_and_budgets(db):
    setup(db, cascade=True)
    c = db.collection("docs")
    refs = [c.ref(c.insert({"i": i}, id=str(i))) for i in range(4)]
    r = db.relationship("links")
    for a, b in [(0, 0), (0, 1), (1, 2), (2, 0), (0, 3)]:
        r.connect(refs[a], refs[b])
    with pytest.raises(AlreadyExistsError):
        r.connect(refs[0], refs[1])
    assert [(v["ref"].id, v["depth"]) for v in r.neighbors(refs[0], depth=5)] == [("1", 1), ("3", 1), ("2", 2)]
    assert [v["ref"].id for v in r.neighbors(refs[0], direction="in")] == ["2"]
    for kwargs in [{"max_nodes": 1}, {"max_edges": 1}]:
        with pytest.raises(TraversalLimitError):
            r.neighbors(refs[0], depth=4, **kwargs)
    c.delete("1")
    assert [e["target_id"] for e in r.edges(refs[0])] == ["0", "3"]


def test_fk_and_references(db):
    setup(db)
    c = db.collection("docs")
    a, b = c.insert({}), c.insert({})
    r = db.relationship("links")
    r.connect(c.ref(a), c.ref(b))
    with pytest.raises(ConstraintError):
        c.delete(a["id"])
    with melddb.open(":memory:") as other:
        with pytest.raises(ValidationError):
            r.connect(c.ref(a), other.collection("docs").ref(b))
    with pytest.raises(ConstraintError):
        r.connect(c.ref(a), c.ref("missing"))


def test_migration_evolution(db):
    if db._backend.pg:
        pytest.skip("Published PostgreSQL proof excludes schema evolution")
    c = db.collection("docs")
    bad = c.insert({"v": "x"})
    with pytest.raises(ValidationError) as error:
        db.migrate(Migration("001", (s.require("docs", "title"),)))
    assert error.value.violations
    assert db.inspect()["migrations"] == []
    c.replace(bad["id"], {"title": "good", "v": 1})
    m = Migration("001", (s.require("docs", "title"), s.type_of("docs", "v", type="number"),
                          s.index("docs", "title", unique=True)))
    db.migrate(m)
    db.migrate(m)
    with pytest.raises(MigrationError):
        db.migrate(Migration("001", (s.require("docs", "v"),)))
    with pytest.raises(ConstraintError):
        c.insert({"v": 2})
    with pytest.raises(AlreadyExistsError):
        c.insert({"title": "good"})
    physical = db.inspect()["objects"][0]["physical"]
    with pytest.raises(ConstraintError):
        db.sql(f'UPDATE "{physical}" SET body=?', (json.dumps({}),))
    assert db.check()["ok"]


def test_reopen_and_isolation(tmp_path):
    path = tmp_path / "bare.db"
    with melddb.open(path) as a, melddb.open(tmp_path / "other.db") as b:
        a.collection("x").insert({"v": 1}, id="a")
        b.collection("x").insert({"v": 2}, id="a")
    with melddb.open(path) as a:
        assert a.collection("x").get("a")["body"] == {"v": 1}
    conn = sqlite3.connect(path)
    conn.execute("UPDATE _melddb_format SET version=99")
    conn.commit()
    conn.close()
    with pytest.raises(MigrationError):
        melddb.open(path)


@pytest.mark.parametrize("kind", ["collection", "table"])
def test_raw_sql_cannot_null_or_change_identity(db, kind):
    operation = s.collection("records") if kind == "collection" else s.table("records", {"n": "integer"})
    db.migrate(Migration("001", (operation,)))
    storage = getattr(db, kind)("records")
    storage.insert({"n": 1}, id="original")
    physical = db.inspect()["objects"][0]["physical"]
    with pytest.raises(ConstraintError):
        db.sql(f'UPDATE "{physical}" SET id=\'changed\'')
    with pytest.raises(ConstraintError):
        db.sql(f'UPDATE "{physical}" SET id=NULL')
    values = "NULL,1,'{}'" if kind == "collection" else "NULL,1"
    with pytest.raises(ConstraintError):
        db.sql(f'INSERT INTO "{physical}" VALUES ({values})')
    assert storage.get("original") is not None
    assert len(storage.find()) == 1


def test_shared_json_contract(db):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "json_contract.json").read_text(
        encoding="utf-8"
    ))
    collection = db.collection("fixture")
    for record in fixture["records"]:
        assert collection.insert(record["body"], id=record["id"])["body"] == record["body"]
    for case in fixture["queries"]:
        predicate = getattr(field(*case["path"]), case["operator"])(*case["arguments"])
        assert [row["id"] for row in collection.find(predicate)] == case["ids"]
    assert [row["id"] for row in collection.find(order_by=field("v"))] == fixture["ordered_ids"]
    assert [row["id"] for row in collection.find(order_by=field("v"), limit=3, offset=2)] == (
        fixture["ordered_ids"][2:5]
    )


def test_postgres_unsupported_revision_has_no_effect(db):
    if not db._backend.pg:
        pytest.skip("PostgreSQL proof boundary")
    with pytest.raises(UnsupportedError):
        db.migrate(Migration("001", (s.collection("new"), s.require("new", "name"))))
    assert db.inspect()["objects"] == []
    assert db.inspect()["migrations"] == []


def test_logical_mixed_transfer_proof(db, tmp_path):
    with melddb.open(tmp_path / "source.db") as source:
        setup(source)
        with source.transaction() as tx:
            docs = tx.collection("docs")
            a = docs.insert({"name": "a"}, id="a")
            b = docs.insert({"name": "b"}, id="b")
            docs.replace("a", {"name": "revised"}, expected_version=1)
            tx.relationship("links").connect(docs.ref(a), docs.ref(b))
            tx.table("rows").insert({"name": "event", "n": 2**63-1}, id="event")
        source.export(tmp_path / "transfer.json")
    db.import_into(tmp_path / "transfer.json")
    assert db.collection("docs").get("a") == {
        "id": "a", "version": 2, "body": {"name": "revised"},
    }
    assert db.table("rows").get("event")["n"] == 2**63-1
    assert db.relationship("links").edges(db.collection("docs").ref("a")) == [
        {"source_id": "a", "target_id": "b", "properties": {}},
    ]
