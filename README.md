# MeldDB

MeldDB is a Python library for using JSON documents, relational tables, and
persistent relationships together in one embedded database.

Its governing rule is **plain data in, plain data out; all database I/O is
explicit**. MeldDB does not use model base classes, identity maps, automatic
flushing, lazy loading, or tracked objects.

> [!NOTE]
> MeldDB is an early alpha. SQLite is the primary backend. PostgreSQL support
> is an experimental portability proof and requires the `postgres` extra.

## Example

```python
import melddb

with melddb.open("application.db") as db:
    manifest = db.collection("manifests").insert(
        {"name": "example", "version": 1}
    )

    with db.transaction() as tx:
        tx.collection("manifests").replace(
            manifest["id"],
            {"name": "example", "version": 2},
        )
```

Collections may be created on their first insert. Managed tables and
relationships are declared through explicit, checksummed migrations.

## Development

MeldDB requires Python 3.12 or newer. The core package has no third-party
runtime dependencies.

```console
uv run --extra test pytest
uv run --extra test ruff check .
uv run python examples/workflows.py .demo
```

The inspector CLI exposes managed structure and validation without hiding the
underlying SQL database:

```console
uv run melddb inspect application.db
uv run melddb check application.db
```

## Current scope

- Detached dictionaries, scalars, and immutable references
- Explicit transactions shared by collections, tables, and relationships
- Optimistic document versions and stable library errors
- Bounded portable predicates and deterministic pagination
- Declared directed relationships with real foreign keys
- Bounded breadth-first traversal
- Checksummed migrations and database-enforced constraints
- Inspection, SQLite backup, and checksummed logical transfer
- Raw parameterized SQL access

See `examples/workflows.py` for an executable mixed-data workflow.

The [delivery plan](docs/implementation-plan.md) tracks the remaining gates.
The [backend matrix](docs/backend-matrix.md) describes the experimental
PostgreSQL boundary, with [local validation evidence](docs/validation.md).
Passing prototype tests does not yet qualify SQLite as a supported release.
