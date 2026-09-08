# Directed relationships

Declare each relationship in a migration, fixing its source and target collection
or managed table. Each has its own SQL edge table, endpoint foreign keys and a
unique source/target pair. No object hydration or implicit persistence occurs.

```python
db.migrate(Migration("001", (
    schema.collection("packages"),
    schema.relationship("depends_on", "packages", "packages", on_delete="cascade"),
)))
packages = db.collection("packages")
app = packages.insert({"name": "app"})
parser = packages.insert({"name": "parser"})
links = db.relationship("depends_on")
links.connect(packages.ref(app["id"]), packages.ref(parser["id"]), {"optional": False})
reachable = links.neighbors(packages.ref(app["id"]), depth=4)
```

Imports are `import melddb`, `from melddb import Migration, schema`; open `db`
with `melddb.open(...)`. Run the complete example with
`uv run python examples/dependencies.py`.

## Writes and identities

`connect(source, target, properties=None)` inserts one link. A duplicate raises
`AlreadyExistsError`; it never updates existing properties. Properties are a
portable JSON object, defaulting to `{}`. `replace_properties(source, target,
properties)` replaces that complete object and returns whether the link exists.
`disconnect(source, target)` returns whether a link was deleted. Returned
properties and records are detached; mutate them locally without changing storage.

References must belong to this database handle and the declared endpoint storage.
Invalid references raise `ValidationError`; nonexistent endpoint rows fail the
foreign-key constraint. Equal IDs in different stores identify different records.
With `properties=False`, only empty properties are accepted.

Deletion defaults to `restrict`: incident links prevent endpoint deletion.
`on_delete="cascade"` deletes incident links when either endpoint is deleted.
It does not delete the other endpoint. These rules apply to SQL writes while
foreign-key enforcement is enabled. Self-links and cycles are permitted.

Standalone writes are atomic. Use `tx.relationship(...)` inside an explicit
transaction to share changes with documents and table rows. An operation failure
poisons that transaction even when its exception is caught.

## Listing and traversal

`edges(ref, direction="out", limit=100, offset=0)` returns dictionaries with
`source_id`, `target_id` and `properties`. Use `direction="in"` for incoming
links. Results use case-sensitive binary ordering of the opposite endpoint ID.
Limit is 1–10,000; offset is 0–2**63-1. Boolean pagination arguments are invalid.

`neighbors(ref, direction="out", depth=1, max_nodes=10000, max_edges=50000)`
returns dictionaries with immutable `ref`, detached `record`, and minimum `depth`.
Records use their collection envelope or table dictionary. Results are unique,
sorted by depth then case-sensitive ID. The starting record is excluded; an ID
equal to the start in a different endpoint store is still a distinct result.
An existing or nonexistent reference without incident links returns an empty list.

Traversal repeats this declared relationship only. Different source/target stores
naturally end traversal at one hop, even if greater depth is requested. For a
relationship within one store, visited tracking prevents repeated expansion of
cycles and self-links. Incoming traversal reverses the same edges.

The node budget includes the starting record, for every endpoint combination.
The edge budget counts every examined edge, including self-links and edges to
already visited nodes. Reaching either budget exactly is allowed; exceeding one
raises `TraversalLimitError` without returning partial results. Depth and budgets
must be integers from 1 through 2**63-2; booleans are invalid.

Standalone traversal uses one read transaction for discovery and record retrieval.
Operations within an explicit caller transaction inherit that transaction's
backend isolation; identical isolation across adapters is not promised. Queries
batch up to 400 frontier IDs and 400 returned records, avoiding one query per node.

## S07 scale evidence

`uv run python validation/traversal_scale.py` builds 10,000 documents and 50,000
edges, compares complete traversal results with a sqlite3 baseline, checks exact
edge-budget overflow, and validates database integrity. Both traversals use
51 batched SELECTs to return 9,999 records, with depth two examining all 50,000
edges. The MeldDB operation issues 57 SQL statements including metadata queries.

The [recorded Windows sample](s07-scale-results.json) measured about 74 ms for
MeldDB traversal and 54 ms for sqlite3. Insertion took 1.45 s through the checked
per-record API and 0.13 s through driver `executemany`, each in one transaction.
The baseline has fewer structural checks. These single samples establish bounded
query counts and a measurable overhead, not universal performance claims.

Shared SQLite/PostgreSQL tests also compare generated cyclic graphs with an
in-memory breadth-first implementation in both directions, verify concurrent
snapshot reads, and cover all collection/table endpoint and deletion-policy pairs.
