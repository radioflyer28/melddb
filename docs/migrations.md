# Explicit schema evolution

Use `db.migrate(Migration("001", (...operations...)), ...)`. IDs are nonempty
strings ordered lexicographically with case-sensitive binary ordering on both
backends. Zero-pad numerical IDs. Operations use the constructors in
`melddb.schema`; unknown fields, invalid values and malformed declarations raise
`ValidationError`. A request is validated before its first schema mutation.

One call is one write transaction, including every supplied revision. A later
failure rolls back earlier revisions in that call, all created SQL objects and
metadata. Previously committed revisions remain intact. Run migrations outside
an application transaction; `tx` does not expose `migrate`.

The operation sequence is stored with a SHA-256 checksum of canonical JSON.
Replaying the same ID and checksum is harmless. Changing its content raises
`MigrationError`, as does inserting a new revision before the latest recorded
ID. Repair a failed revision's input/data and retry it only when it was never
committed; otherwise append a new revision. There is no automatic schema diff.

## Supported operations

| Constructor | Behavior |
| --- | --- |
| `collection(name)` | Create an ordinary document table |
| `table(name, columns)` | Create a managed scalar table with immutable text ID |
| `relationship(name, source, target, ...)` | Create declared directed edges and foreign keys |
| `require(name, *path)` | Reject missing or null values |
| `type_of(name, *path, type=...)` | Constrain present, non-null document values |
| `index(name, *path, unique=False)` | Add a scalar path or ordinary column index |

The PostgreSQL proof supports creation only. Any evolution operation causes
the entire request to fail with `UnsupportedError` before schema mutation,
including when a creation revision precedes it. This is an intentional capability
boundary, not a claim of PostgreSQL migration parity.

SQLite table paths contain exactly one declared column. Table types are fixed
at creation; changing them is unsupported. Document paths traverse object keys
only, including quoted or unusual keys. Arrays and wildcard traversal are not
supported. Primitive document types are `string`, `number`, `integer` and
`boolean`; `number` permits integer and real JSON values, while `integer` requires
the JSON integer representation. Booleans do not count as numbers. Type rules
permit missing/null values; combine them with `require` when needed.

Document uniqueness includes only scalar values. Missing, null, objects and
arrays do not participate. Combine a primitive type rule and `require` when
every document must provide a unique scalar. Numbers compare numerically, so
1 and 1.0 collide; true, 1 and "1" remain distinct. String uniqueness is case
sensitive. Nullable table columns likewise exclude null from uniqueness.

An identical constraint/index declaration repeated in later revisions is a
no-op, while that revision is still recorded. Identical creation declarations
are also harmless; differing declarations for an existing store fail. Table
column names reject ASCII case duplicates (including variants of reserved `id`)
to preserve behavior across SQLite and PostgreSQL.

## Validation and enforcement

SQLite obtains a write lock before validating existing rows, retaining it
through installation and commit. A competing process cannot insert invalid data
between validation and installation. Contention raises a stable error; the
library does not retry a transaction automatically.

When existing data fails a proposed rule, `ValidationError.violations` reports
up to 100 rows sorted by ID for the first failing operation:

```python
{"storage": "contacts", "path": ["email"], "rule": "require", "id": "ada"}
{"storage": "contacts", "path": ["email"], "rule": "index", "id": "ada", "count": 2}
```

For uniqueness, `count` is the full duplicate group size even when the diagnostic
list is capped. Nothing is coerced, deleted or partly installed. Fix application
data explicitly and retry. See `examples/schema_evolution.py` for that workflow.

SQLite uses native checks, triggers and partial expression indexes, with no
Python callbacks. They enforce supported invariants for direct sqlite3 writes
as well as SDK calls. External connections must enable foreign keys and must
not disable checks or remove managed objects. Raw SQL retains driver affinity
and conversion behavior; it does not acquire SDK JSON validation or version
increments. Managed metadata is private. `inspect()` exposes physical mappings
for SQL inspection, not a permanently fixed physical schema.

## Recovery and boundary

Process-crash tests terminate after trigger/index creation, metadata updates,
revision insertion, and commit. Reopening finds either the complete committed
revision or the prior state, passes integrity/FK checks, and accepts a retry.
These tests simulate process interruption, not all power-loss/filesystem failures.

Renames, drops, type conversions, user-table adoption, and automatic reshaping
remain excluded. Storage format stays at version 2; unsupported metadata
versions fail at open. Deep detection of externally altered managed objects
belongs to S09 structural verification.
