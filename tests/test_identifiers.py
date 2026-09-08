"""UUIDv7 layout, clock behavior and backward-compatible text identities."""
from uuid import RFC_4122, UUID, uuid4

import pytest

from melddb import Migration, identifiers
from melddb import schema as s
from melddb.errors import ValidationError


@pytest.mark.parametrize("random", [0, 1, 2**62, 2**74-1])
def test_uuid7_layout(monkeypatch, random):
    milliseconds = 0x0123456789AB
    monkeypatch.setattr(identifiers, "time_ns", lambda: milliseconds * 1_000_000)
    monkeypatch.setattr(identifiers, "randbits", lambda bits: random if bits == 74 else None)
    value = UUID(identifiers.new_id())
    assert value.version == 7 and value.variant == RFC_4122
    assert value.int >> 80 == milliseconds
    recovered = (((value.int >> 64) & 0xFFF) << 62) | (value.int & (2**62-1))
    assert recovered == random


def test_uuid7_randomness_and_clock_rollback(monkeypatch):
    monkeypatch.setattr(identifiers, "time_ns", lambda: 1000 * 1_000_000)
    values = {identifiers.new_id() for _ in range(10000)}
    assert len(values) == 10000
    monkeypatch.setattr(identifiers, "time_ns", lambda: 999 * 1_000_000)
    assert identifiers.new_id() < min(values)
    # IDs group by wall-clock milliseconds; they are not a commit sequence.
    for bad in (-1, 2**48):
        monkeypatch.setattr(identifiers, "time_ns", lambda: bad * 1_000_000)
        with pytest.raises(ValidationError):
            identifiers.new_id()


def test_record_defaults_and_old_ids(db):
    db.migrate(Migration("001", (s.collection("docs"), s.table("rows", {"n": "integer"}))))
    for store in (db.collection("docs"), db.table("rows")):
        assert UUID(store.insert({"n": 1})["id"]).version == 7
        for old in (str(uuid4()), "application-id"):
            store.insert({"n": 2}, id=old)
            assert store.get(old)["id"] == old


def test_managed_document_index_is_used(tmp_path):
    import melddb
    from melddb import field
    from melddb.query import compile_predicate
    with melddb.open(tmp_path / "indexed.db") as db:
        db.migrate(Migration("001", (s.collection("docs"), s.index("docs", "key"))))
        db.collection("docs").insert({"key": "needle"})
        spec = db.inspect()["objects"][0]
        predicate, params = compile_predicate(field("key").eq("needle"), spec["schema"])
        plan = db.sql(f'EXPLAIN QUERY PLAN SELECT * FROM "{spec["physical"]}" WHERE {predicate}', params)
        assert any("USING INDEX ad_idx_" in row["detail"] for row in plan)
