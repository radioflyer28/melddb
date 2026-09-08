"""S07 directed relationship behavior and traversal reference checks."""
from collections import deque

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import melddb
from melddb import Migration, Ref
from melddb import schema as s
from melddb.errors import (
    AlreadyExistsError,
    ConstraintError,
    TransactionError,
    TraversalLimitError,
    ValidationError,
)


def graph(db, source="collection", target="collection", same=True, policy="restrict", props=True):
    operations = [s.collection("nodes") if source == "collection" else s.table("nodes", {"n": "integer"})]
    if not same:
        operations.append(s.collection("targets") if target == "collection" else s.table("targets", {"n": "integer"}))
    operations.append(s.relationship("edges", "nodes", "nodes" if same else "targets",
                                     on_delete=policy, properties=props))
    db.migrate(Migration("001", tuple(operations)))
    a = getattr(db, source)("nodes")
    b = a if same else getattr(db, target)("targets")
    return a, b, db.relationship("edges")


@pytest.mark.parametrize("source,target", [("collection", "collection"), ("collection", "table"),
                                           ("table", "collection"), ("table", "table")])
@pytest.mark.parametrize("policy", ["restrict", "cascade"])
@pytest.mark.parametrize("delete_end", ["source", "target"])
def test_declared_endpoints_deletion_and_same_id(db, source, target, policy, delete_end):
    a, b, edges = graph(db, source, target, same=False, policy=policy)
    ar, br = a.ref(a.insert({"n": 1}, id="same")), b.ref(b.insert({"n": 2}, id="same"))
    edges.connect(ar, br)
    outgoing = edges.neighbors(ar, depth=5)
    incoming = edges.neighbors(br, direction="in", depth=5)
    assert [(r["ref"], r["depth"]) for r in outgoing] == [(br, 1)]
    assert [(r["ref"], r["depth"]) for r in incoming] == [(ar, 1)]
    with pytest.raises(TraversalLimitError):
        edges.neighbors(ar, max_nodes=1)
    assert len(edges.neighbors(ar, max_nodes=2, max_edges=1)) == 1
    selected = a if delete_end == "source" else b
    if policy == "restrict":
        with pytest.raises(ConstraintError):
            selected.delete("same")
        assert edges.disconnect(ar, br)
        assert not edges.disconnect(ar, br)
        assert selected.delete("same")
    else:
        assert selected.delete("same")
        assert edges.edges(ar) == []


def test_properties_duplicates_and_atomic_mutation(db):
    nodes, _, edges = graph(db)
    a, b = [nodes.ref(nodes.insert({"n": n})) for n in (1, 2)]
    props = {"nested": {"weight": 1}}
    edges.connect(a, b, props)
    props["nested"]["weight"] = 99
    row = edges.edges(a)[0]
    assert row["properties"] == {"nested": {"weight": 1}}
    row["properties"]["nested"]["weight"] = 88
    with pytest.raises(AlreadyExistsError):
        edges.connect(a, b, {"overwrite": True})
    assert edges.edges(a)[0]["properties"] == {"nested": {"weight": 1}}
    assert edges.replace_properties(a, b, {"replacement": None})
    assert not edges.replace_properties(b, a, {})
    with pytest.raises(TransactionError):
        with db.transaction() as tx:
            relation = tx.relationship("edges")
            relation.disconnect(a, b)
            relation.connect(b, a)
            with pytest.raises(AlreadyExistsError):
                relation.connect(b, a)
    assert edges.edges(a)[0]["properties"] == {"replacement": None}
    assert edges.edges(b) == []


@pytest.mark.parametrize("props", [[], {"v": float("nan")}, {"v": 2**53}, {"v": "\x00"}])
def test_invalid_properties(db, props):
    nodes, _, edges = graph(db)
    a = nodes.ref(nodes.insert({}))
    with pytest.raises(ValidationError):
        edges.connect(a, a, props)
    assert edges.edges(a) == []
    edges.connect(a, a)
    with pytest.raises(ValidationError):
        edges.replace_properties(a, a, props)
    assert edges.edges(a)[0]["properties"] == {}


def test_properties_disabled_and_invalid_references(db):
    a, b, edges = graph(db, same=False, props=False)
    ar, br = a.ref(a.insert({})), b.ref(b.insert({}))
    for left, right in [(br, ar), (ar, ar), ("id", br), (Ref("nodes", None, ar._owner), br)]:
        with pytest.raises(ValidationError):
            edges.connect(left, right)
    with melddb.open(":memory:") as other:
        with pytest.raises(ValidationError):
            edges.connect(other.collection("nodes").ref(ar.id), br)
    with pytest.raises(ConstraintError):
        edges.connect(ar, b.ref("absent"))
    with pytest.raises(ValidationError):
        edges.connect(ar, br, {"weight": 1})
    edges.connect(ar, br)
    with pytest.raises(ValidationError):
        edges.replace_properties(ar, br, {"weight": 1})
    assert edges.replace_properties(ar, br, {})


def test_exact_budgets_cycles_and_minimum_depth(db):
    nodes, _, edges = graph(db)
    refs = {i: nodes.ref(nodes.insert({}, id=i)) for i in "abcd"}
    for a, b in [("a", "a"), ("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "a")]:
        edges.connect(refs[a], refs[b])
    assert [(r["ref"].id, r["depth"]) for r in edges.neighbors(refs["a"], depth=10, max_nodes=4, max_edges=6)] == [
        ("b", 1), ("c", 1), ("d", 2),
    ]
    assert [r["ref"].id for r in edges.neighbors(refs["a"])] == ["b", "c"]
    for options in [{"max_nodes": 3}, {"max_edges": 5}]:
        with pytest.raises(TraversalLimitError):
            edges.neighbors(refs["a"], depth=10, **options)


@pytest.mark.parametrize("options", [{"depth": 0}, {"depth": True}, {"max_nodes": -1},
                                     {"max_edges": 2**63}, {"direction": "both"}])
def test_invalid_traversal_options(db, options):
    nodes, _, edges = graph(db)
    with pytest.raises(ValidationError):
        edges.neighbors(nodes.ref("absent"), **options)


def test_edge_pagination(db):
    nodes, _, edges = graph(db)
    root = nodes.ref(nodes.insert({}, id="root"))
    for ident in ["z", "A", "a", "Z"]:
        edges.connect(root, nodes.ref(nodes.insert({}, id=ident)))
    assert [row["target_id"] for row in edges.edges(root, limit=2, offset=1)] == ["Z", "a"]
    with pytest.raises(ValidationError):
        edges.edges(root, offset=2**63)


def test_wide_frontier_is_batched(db, monkeypatch):
    nodes, _, edges = graph(db)
    root = nodes.ref(nodes.insert({}, id="root"))
    with db.transaction() as tx:
        for i in range(1001):
            leaf = tx.collection("nodes").insert({}, id=f"leaf{i:04}")
            tx.relationship("edges").connect(root, nodes.ref(leaf))
    execute = db._backend.execute
    queries = []
    def counted(statement, *args, **kwargs):
        if "WHERE" in statement and " IN (" in statement:
            queries.append(statement)
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db._backend, "execute", counted)
    result = edges.neighbors(root, depth=2)
    assert len(result) == 1001
    # 1 root expansion + 3 frontier batches + 3 record hydration batches.
    assert len(queries) == 7


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.sets(st.tuples(st.integers(0, 6), st.integers(0, 6)), max_size=20),
       st.sampled_from(["in", "out"]), st.integers(1, 8))
def test_reference_bfs(db, links, direction, depth):
    nodes, _, relation = graph(db, policy="cascade")
    for row in nodes.find():
        nodes.delete(row["id"])
    refs = [nodes.ref(nodes.insert({}, id=str(i))) for i in range(7)]
    for a, b in links:
        relation.connect(refs[a], refs[b])
    oriented = links if direction == "out" else {(b, a) for a, b in links}
    seen, queue = {0: 0}, deque([0])
    while queue:
        source = queue.popleft()
        if seen[source] == depth:
            continue
        for a, b in oriented:
            if a == source and b not in seen:
                seen[b] = seen[a] + 1
                queue.append(b)
    seen.pop(0)
    actual = {int(r["ref"].id): r["depth"] for r in relation.neighbors(refs[0], direction=direction, depth=depth)}
    assert actual == seen


def test_traversal_uses_one_snapshot(db, monkeypatch):
    nodes, _, edges = graph(db, policy="cascade")
    a, b = nodes.ref(nodes.insert({"n": 1})), nodes.ref(nodes.insert({"n": 2}))
    edges.connect(a, b)
    other = melddb.connect(db._backend.path) if db._backend.pg else melddb.open(db._backend.path)
    execute = db._backend.execute
    changed = False
    def interleaved(statement, *args, **kwargs):
        nonlocal changed
        rows = execute(statement, *args, **kwargs)
        if "AS id FROM" in statement and not changed:
            changed = True
            other.collection("nodes").delete(b.id)
        return rows
    try:
        monkeypatch.setattr(db._backend, "execute", interleaved)
        result = edges.neighbors(a)
        assert result[0]["record"]["body"] == {"n": 2}
        assert changed
    finally:
        other.close()
    assert nodes.get(b.id) is None
