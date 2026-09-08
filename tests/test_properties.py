from collections import deque

from hypothesis import given, settings
from hypothesis import strategies as st

import melddb
from melddb import Migration, field
from melddb import schema as s

strings = st.text(st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"), max_size=20)
scalars = st.none() | st.booleans() | st.integers(-(2**53-1), 2**53-1) | strings
jsons = st.recursive(scalars, lambda children: st.lists(children, max_size=4) |
                    st.dictionaries(strings, children, max_size=4), max_leaves=15)


@settings(max_examples=80, deadline=None)
@given(st.dictionaries(strings, jsons, max_size=5))
def test_json_roundtrip(body):
    with melddb.open(":memory:") as db:
        c = db.collection("docs")
        row = c.insert(body)
        assert c.get(row["id"])["body"] == body


@settings(max_examples=60, deadline=None)
@given(st.lists(st.integers(-1000, 1000), max_size=30), st.integers(-1000, 1000))
def test_numeric_predicate_reference(values, threshold):
    with melddb.open(":memory:") as db:
        c = db.collection("numbers")
        for i, value in enumerate(values):
            c.insert({"n": value}, id=f"{i:03}")
        assert [row["body"]["n"] for row in c.find(field("n").gte(threshold))] == [
            v for v in values if v >= threshold]


@settings(max_examples=40, deadline=None)
@given(st.sets(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=25), st.integers(1, 5))
def test_reachability_reference(edges, depth):
    with melddb.open(":memory:") as db:
        db.migrate(Migration("001", (s.collection("nodes"), s.relationship("edges", "nodes", "nodes"))))
        c = db.collection("nodes")
        refs = [c.ref(c.insert({}, id=str(i))) for i in range(8)]
        for source, target in edges:
            db.relationship("edges").connect(refs[source], refs[target])
        queue, expected = deque([(0, 0)]), {0: 0}
        while queue:
            source, distance = queue.popleft()
            if distance == depth:
                continue
            for a, b in edges:
                if a == source and b not in expected:
                    expected[b] = distance + 1
                    queue.append((b, distance + 1))
        expected.pop(0)
        actual = {int(row["ref"].id): row["depth"] for row in
                  db.relationship("edges").neighbors(refs[0], depth=depth)}
        assert actual == expected
