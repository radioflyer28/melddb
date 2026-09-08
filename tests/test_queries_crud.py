"""S05/S06 contract tests, run without changes against both adapters."""
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from melddb import Migration, field
from melddb import schema as s
from melddb.errors import ConflictError, NotFoundError, TransactionError, ValidationError


def ids(rows):
    return [r["id"] for r in rows]


def test_object_paths_do_not_traverse_arrays(db):
    c = db.collection("paths")
    c.insert({"x": [{"v": 7}]}, id="array")
    c.insert({"x": {"0": {"v": 7}}}, id="object")
    assert ids(c.find(field("x", "0", "v").eq(7))) == ["object"]
    assert ids(c.find(field("x", "0", "v").is_missing())) == ["array"]
    assert ids(c.find(order_by=field("x", "0", "v"))) == ["array", "object"]


@pytest.mark.parametrize("operator,expected", [
    ("eq", ["n2"]), ("ne", ["n1", "n3"]), ("gt", ["n3"]),
    ("gte", ["n2", "n3"]), ("lt", ["n1"]), ("lte", ["n1", "n2"]),
])
def test_comparison_operator_contract(db, operator, expected):
    c = db.collection("operators")
    for ident, body in [("missing", {}), ("null", {"v": None}), ("bool", {"v": True}),
                        ("string", {"v": "2"}), ("n1", {"v": 1}),
                        ("n2", {"v": 2}), ("n3", {"v": 3.5})]:
        c.insert(body, id=ident)
    assert ids(c.find(getattr(field("v"), operator)(2))) == expected
    assert ids(c.find(~field("v").gte(2))) == ["bool", "missing", "n1", "null", "string"]
    assert ids(c.find(field("v").eq(1) | field("v").eq("2"))) == ["n1", "string"]
    assert ids(c.find(field("v").gte(2) & ~field("v").eq(2))) == ["n3"]


def test_ordering_and_page_boundaries(db):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "ordering.json").read_text())
    c = db.collection("ordering")
    for row in reversed(fixture["records"]):
        c.insert(row["body"], id=row["id"])
    for descending, name in [(False, "ascending"), (True, "descending")]:
        expected = fixture[name]
        assert ids(c.find(order_by=field("v"), descending=descending)) == expected
        actual = []
        for offset in range(0, len(expected), 3):
            actual.extend(ids(c.find(order_by=field("v"), descending=descending, limit=3, offset=offset)))
        assert actual == expected
    assert c.find(offset=100) == []


@pytest.mark.parametrize("options", [
    {"limit": 0}, {"limit": True}, {"limit": 10001}, {"offset": -1}, {"offset": 2**63},
    {"offset": False}, {"descending": "DESC"}, {"columns": ["id"]}, {"where": "x = 1"},
])
def test_invalid_find_rejected_even_without_storage(db, options):
    with pytest.raises(ValidationError):
        db.collection("not_created").find(**options)
    assert db.inspect()["objects"] == []


def test_membership_boundaries(db):
    c = db.collection("membership")
    c.insert({"v": 499})
    assert c.find(field("v").isin([])) == []
    assert len(c.find(field("v").isin(range(500)))) == 1
    with pytest.raises(ValidationError):
        c.find(field("v").isin(range(501)))


@pytest.mark.parametrize("number", [5e-324, -5e-324, 1.7976931348623157e308, -1e308, -0.0])
def test_finite_json_float_boundaries(db, number):
    c = db.collection("float_values")
    record = c.insert({"v": number})
    assert c.get(record["id"])["body"]["v"] == number
    assert ids(c.find(field("v").eq(number))) == [record["id"]]
    assert ids(c.find(order_by=field("v"))) == [record["id"]]


@pytest.mark.parametrize("key", ["\n", "\t", "\\", '"\\\n', "snow\u2603"])
def test_escaped_object_keys(db, key):
    c = db.collection("escaped")
    c.insert({key: {"v": 1}}, id="record")
    assert ids(c.find(field(key, "v").eq(1))) == ["record"]


def test_parameterized_raw_sql_and_existing_tables(db):
    db.sql("CREATE TABLE external_contacts(name TEXT)")
    parameter = "%s" if db._backend.pg else "?"
    value = "'); DROP TABLE external_contacts; --"
    assert db.sql(f"INSERT INTO external_contacts(name) VALUES ({parameter}) RETURNING name", (value,)) == [
        {"name": value},
    ]
    assert db.sql(f"WITH matches AS (SELECT name FROM external_contacts WHERE name={parameter}) "
                  "SELECT name FROM matches", (value,)) == [{"name": value}]
    assert "external_contacts" in db.inspect()["external_tables"]
    with pytest.raises(NotFoundError):
        db.table("external_contacts").get("unmanaged")


def test_replace_delete_and_conditional_conflicts(db):
    c = db.collection("versions")
    original = c.insert({"nested": {"a": 1, "b": 2}, "remove": True}, id="v")
    updated = c.replace("v", {"nested": {"a": 3}}, expected_version=1)
    assert updated == {"id": "v", "version": 2, "body": {"nested": {"a": 3}}}
    assert original["version"] == 1
    updated["body"]["nested"]["a"] = 99
    assert c.get("v")["body"] == {"nested": {"a": 3}}
    for action in [lambda: c.replace("v", {}, expected_version=1),
                   lambda: c.delete("v", expected_version=1),
                   lambda: c.delete("absent", expected_version=1)]:
        with pytest.raises(ConflictError):
            action()
    assert c.delete("v", expected_version=2)
    assert c.get("v") is None
    assert not c.delete("v")
    with pytest.raises(NotFoundError):
        c.replace("v", {})


def test_absent_collection_writes_and_exhausted_version(db):
    c = db.collection("absent")
    assert not c.delete("missing")
    with pytest.raises(ConflictError):
        c.replace("missing", {}, expected_version=1)
    with pytest.raises(ConflictError):
        c.delete("missing", expected_version=1)
    assert db.inspect()["objects"] == []
    c.insert({}, id="exhausted")
    physical = db.inspect()["objects"][0]["physical"]
    db.sql(f'UPDATE "{physical}" SET version=9223372036854775807')
    for version in (None, 2**63-1):
        with pytest.raises(ConflictError):
            c.replace("exhausted", {"changed": True}, expected_version=version)
    assert c.get("exhausted")["version"] == 2**63-1
    assert c.get("exhausted")["body"] == {}


@pytest.mark.parametrize("version", [True, 0, -1, "1", 2**63])
def test_invalid_versions(db, version):
    c = db.collection("versions")
    c.insert({}, id="v")
    for action in [lambda: c.replace("v", {}, expected_version=version),
                   lambda: c.delete("v", expected_version=version)]:
        with pytest.raises(ValidationError):
            action()
    assert c.get("v")["version"] == 1


def declare_table(db):
    db.migrate(Migration("001", (s.table("people", {
        "name": "text", "age": "integer", "rating": "float", "active": "boolean", "photo": "bytes",
    }),)))
    return db.table("people")


def test_relational_full_crud_and_types(db):
    t = declare_table(db)
    row = t.insert({"name": "Ada", "age": -(2**63), "rating": 10**100,
                    "active": False, "photo": b"\x00\xff"}, id="ada")
    assert row["rating"] == 1e100
    assert type(row["rating"]) is float
    row["name"] = "mutated"
    assert t.get("ada")["name"] == "Ada"
    changed = t.update("ada", {"age": 2**63-1, "rating": 10**50, "active": True})
    assert changed["age"] == 2**63-1 and changed["rating"] == 1e50
    assert t.find(field("rating").eq(10**50), columns=["name", "photo", "active"]) == [
        {"name": "Ada", "photo": b"\x00\xff", "active": True},
    ]
    empty = t.insert({}, id="empty")
    assert all(empty[c] is None for c in ("name", "age", "rating", "active", "photo"))
    assert ids(t.find(field("name").is_null())) == ["empty"]
    assert t.find(field("name").is_missing()) == []
    assert ids(t.find(field("active").eq(True))) == ["ada"]
    assert t.delete("ada") and not t.delete("ada")
    assert t.get("ada") is None
    with pytest.raises(NotFoundError):
        t.update("ada", {"name": "missing"})


@pytest.mark.parametrize("changes", [
    {"age": True}, {"age": 2**63}, {"age": -(2**63)-1}, {"age": 1.5},
    {"rating": 10**1000}, {"rating": float("nan")}, {"rating": float("inf")},
    {"rating": True}, {"active": 1}, {"photo": "bytes"}, {"name": "\x00"},
    {"name": "\ud800"}, {"id": "changed"}, {"unknown": 1},
])
def test_relational_invalid_values_atomic(db, changes):
    t = declare_table(db)
    original = t.insert({"name": "original"}, id="v")
    with pytest.raises(ValidationError):
        t.insert(changes)
    with pytest.raises(ValidationError):
        t.update("v", changes)
    assert t.find() == [original]


@pytest.mark.parametrize("columns", ["name", [], ["unknown"], [None], [["name"]]])
def test_invalid_projection(db, columns):
    t = declare_table(db)
    with pytest.raises(ValidationError):
        t.find(columns=columns)


def test_relational_ordering_and_poisoned_query(db):
    t = declare_table(db)
    for ident, name in [("z", "same"), ("Z", "same"), ("a", "same"), ("A", "same"),
                         ("null", None), ("capital", "Alpha")]:
        t.insert({"name": name}, id=ident)
    assert ids(t.find(order_by="name")) == ["null", "capital", "A", "Z", "a", "z"]
    assert ids(t.find(order_by="name", descending=True)) == ["null", "A", "Z", "a", "z", "capital"]
    assert ids(t.find(field("name").eq("Same"))) == []
    assert ids(t.find(order_by="name", limit=2, offset=2)) == ["A", "Z"]
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            tx.table("people").insert({"name": "rollback"})
            with pytest.raises(ValidationError):
                tx.table("people").find(columns="name")
    assert t.find(field("name").eq("rollback")) == []


@settings(max_examples=30, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.one_of(st.none(), st.booleans(), st.integers(-50, 50),
                        st.sampled_from(["a", "1", "", 0.5])), max_size=20),
       st.integers(-50, 50))
def test_predicates_against_reference(db, values, threshold):
    c = db.collection("generated")
    with db.transaction() as tx:
        docs = tx.collection("generated")
        for old in docs.find():
            docs.delete(old["id"])
        for i, value in enumerate(values):
            docs.insert({"v": value}, id=f"{i:03}")
    expected = [f"{i:03}" for i, v in enumerate(values)
                if type(v) in (int, float) and v >= threshold]
    assert ids(c.find(field("v").gte(threshold))) == expected
    assert ids(c.find(~field("v").gte(threshold))) == [
        f"{i:03}" for i in range(len(values)) if f"{i:03}" not in expected
    ]
