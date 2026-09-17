# MeldDB

MeldDB is a Python library for storing JSON documents, relational rows, and
persistent relationships in one database. It is designed for desktop applications,
CLI tools, and small local services.

**Plain data in, plain data out; all database I/O is explicit.** Results are
ordinary dictionaries and scalars. There are no model base classes, tracked
objects, automatic flushing, or lazy loading.

> MeldDB 0.1.0rc1 is a candidate for controlled beta testing, not a qualified
> supported release. Windows/Linux Python 3.12-3.14 have qualification evidence;
> macOS qualification remains open. PostgreSQL is experimental. See the
> [beta guide](docs/beta-testing.md) before adopting it.

## Install locally

Python 3.12 or newer is required. The core package has no third-party runtime
dependencies. No package has been published; install from your local checkout:

```console
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in Windows PowerShell, or
`source .venv/bin/activate` on macOS/Linux. From the repository root, run:

```console
python -m pip install .
python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

For a pinned beta artifact instead, install the provided wheel:

```console
python -m pip install ./dist/melddb-0.1.0rc1-py3-none-any.whl
```

SQLite 3.38+ is required, but the version alone is insufficient. MeldDB checks
required JSON-path behavior on open and raises `UnsupportedError` if the loaded
SQLite cannot provide it. Use a Python distribution with a compatible SQLite;
see [verified versions and limitations](docs/release-qualification.md).

## First document: store, query, update, reopen

Run this as a Python script. Collection handles do not create storage; the first
insert creates a collection transactionally. Settings need no schema declaration.

```python
import melddb
from melddb import field

with melddb.open("settings.db") as db:
    settings = db.collection("settings")
    saved = settings.insert({"theme": "dark", "display": {"scale": 2}})
    # saved is {"id": "...", "version": 1, "body": {...}}
    record_id = saved["id"]
    assert settings.get(record_id) == saved

    matches = settings.find(field("display", "scale").gte(2), limit=20)
    assert any(item["id"] == record_id for item in matches)

    # Results are detached. Persist the changed body explicitly.
    saved["body"]["theme"] = "light"
    updated = settings.replace(
        record_id, saved["body"], expected_version=saved["version"]
    )
    assert updated["version"] == 2

with melddb.open("settings.db") as db:
    settings = db.collection("settings")
    assert settings.get(record_id)["body"]["theme"] == "light"
    assert settings.delete(record_id, expected_version=updated["version"])
    assert settings.get(record_id) is None
```

`replace` replaces the entire body, including nested fields. It does not merge.
A stale `expected_version` raises `melddb.errors.ConflictError`. Generated IDs
are UUIDv7 strings; use `insert(body, id="your-text-id")` for an explicit ID.
UUIDv7 does not guarantee insertion or commit ordering.

Document predicates address fields inside `body`. Use `field("x").is_null()`
for explicit null and `.is_missing()` for an absent field; ordinary comparisons
exclude both. Combine predicates with parenthesized `&`, `|`, and `~` expressions.
`find` returns a list, defaults to 100 results, and supports bounded `limit`,
`offset`, and `order_by`; it does not implicitly retrieve every record.
See [query semantics and pagination](docs/queries-and-crud.md).

## Tables and relationships in one transaction

Tables and relationships require explicit migrations. This example uses a
separate database so its schema history is independent of the settings example.
Reapplying the same migration is safe; changing an applied migration is rejected.
Add a new ordered migration ID for later schema changes.

```python
import melddb
from melddb import Migration, field, schema

with melddb.open("project.db") as db:
    db.migrate(Migration("001", (
        schema.table("contacts", {"name": "text", "active": "boolean"}),
        schema.collection("notes"),
        schema.relationship("authored", "contacts", "notes"),
    )))

    with db.transaction() as tx:
        contacts = tx.table("contacts")
        notes = tx.collection("notes")
        ada = contacts.insert({"name": "Ada", "active": True})
        note = notes.insert({"title": "First note", "priority": 1})
        tx.relationship("authored").connect(contacts.ref(ada), notes.ref(note))

    contacts = db.table("contacts")
    contacts.update(ada["id"], {"name": "Ada L."})
    names = contacts.find(field("active").eq(True), columns=["name"])
    linked = db.relationship("authored").neighbors(contacts.ref(ada))
    assert linked[0]["record"] == note
    print(names)
```

Tables return flat row dictionaries with an immutable text `id`. Their `update`
changes only the supplied columns. Supported columns are `text`, `integer`
(signed 64-bit), `float` (finite), `boolean`, and `bytes`. JSON bodies require
finite numbers, integers within +/- (2**53-1), and valid Unicode without NUL.
Encode timestamps, decimals, and larger exact JSON numbers explicitly.

Relationships are directed, with declared endpoint types and unique endpoint
pairs. The default deletion policy restricts deleting linked records. Explicit
`on_delete="cascade"` removes incident links when an endpoint is deleted; it does
not delete neighboring records. Build references with the owning handle's `ref`.
See [relationships](docs/relationships.md) and [migrations](docs/migrations.md).

## Transaction and connection rules

- Each standalone write commits atomically. Use `with db.transaction() as tx`
  to commit related operations together; exceptions roll everything back.
- Inside that block, use only `tx` and handles obtained from it. Ordinary `db`
  operations are rejected while the transaction is active.
- A failed operation makes the transaction unusable, even if its exception is
  caught inside the block. Catch failures outside the transaction and start a
  new transaction if retrying is appropriate. MeldDB does not retry for you.
- Nested transactions are rejected. Transaction handles expire after exit.
- Each database handle is confined to its creating thread. Use separate handles
  for concurrent threads/processes; references cannot cross database handles.
- New SQLite databases use WAL, FULL synchronous writes, foreign keys, and a
  five-second busy timeout. Configure waiting with `melddb.open(path, timeout=5)`.

## SQL, inspection, and recovery

Use parameterized SQL for existing tables or operations outside the portable API:

```python
import melddb

with melddb.open("external.db") as db:
    db.sql("CREATE TABLE IF NOT EXISTS measurements (value INTEGER)")
    db.sql("INSERT INTO measurements VALUES (?)", (42,))
    rows = db.sql("WITH m AS (SELECT MAX(value) AS n FROM measurements) SELECT n FROM m")
    assert rows == [{"n": 42}]
    assert db.check()["ok"]
```

SQL uses the driver's dialect and parameter syntax (`?` for SQLite, `%s` for
PostgreSQL). It does not automatically increment managed document versions.
`db.inspect()` exposes physical table mappings. External tables remain accessible
through SQL; obtaining a managed table handle does not adopt an external schema.

For an existing database, the installed CLI can inspect or create recovery artifacts:

```console
melddb inspect project.db
melddb check project.db
melddb backup project.db project-backup.db
melddb export project.db project-export.json
```

Use fresh artifact destinations. A physical SQLite backup includes external tables;
a logical export includes managed data and lists exclusions. Restore a backup by
opening its new file and checking it. Import a logical export into a new or empty
database with `db.import_into("project-export.json")`, then verify `db.check()` and
your application records. Use the backup API instead of copying an active database.
See [recovery procedures](docs/inspection-and-recovery.md) and
[logical transfer](docs/logical-format.md).

## Experimental PostgreSQL

Install its optional dependency from the checkout with
`python -m pip install ".[postgres]"`. Use `melddb.connect(url)` with a PostgreSQL
connection URL supplied by your application configuration. The same supported
operations use this handle, but isolation and concurrency are backend-dependent.

PostgreSQL currently proves a subset: full schema evolution, equivalent structural
checking, and general hosted cutover are not complete. Read the
[capability matrix](docs/backend-matrix.md) before choosing it. Physical backup is
SQLite-only. libSQL and a production TypeScript SDK are future work.

## Runnable examples and further reading

From the checkout after installation, use a **new output directory for each run**:

```console
python examples/workflows.py .demo-first-run
python examples/query_crud.py .demo-query-run
```

[workflows.py](examples/workflows.py) demonstrates settings, address-book rows,
package dependencies, activity retention, existing SQL, rollback, reopen, backup,
and logical restoration. [query_crud.py](examples/query_crud.py) expands queries,
updates, and conflicts. More examples cover [relationships](examples/dependencies.py),
[schema evolution](examples/schema_evolution.py), [recovery](examples/recovery.py),
and [logical transfer](examples/logical_transfer.py).

- [Beta guide and feedback checklist](docs/beta-testing.md)
- [Queries and CRUD reference](docs/queries-and-crud.md)
- [Relationships](docs/relationships.md) and [migrations](docs/migrations.md)
- [Inspection and recovery](docs/inspection-and-recovery.md)
- [Logical format and portability](docs/logical-format.md)
- [Release qualification](docs/release-qualification.md) and [validation](docs/validation.md)
- [Product comparison](docs/gate-a.md), [delivery plan](docs/implementation-plan.md),
  and [future roadmap](docs/roadmap.md)

Cacheness is a prospective consumer of MeldDB. Its adapter and end-to-end
integration belong in the Cacheness repository; MeldDB stays independent.

## License

MeldDB is licensed under [Apache-2.0](LICENSE). Optional dependencies retain
their own licenses. The core remains free of third-party runtime dependencies.

## Development

```console
uv run --extra test pytest
uv run --extra test ruff check .
```

PostgreSQL conformance setup is documented in the backend matrix. No package is
published automatically. Existing release artifacts have their own recorded
qualification hashes; documentation changes do not rebuild or requalify them.
