# Backend contract during the alpha

SQLite is the intended supported backend; release qualification is still open.
PostgreSQL remains experimental, even where the shared tests pass.

| Operation | SQLite alpha | PostgreSQL proof |
| --- | --- | --- |
| Documents, versions, detached values | Shared tests | Shared tests |
| Managed scalar tables and projections | Shared tests | Shared tests |
| Mixed explicit transactions and failure rollback | Shared tests | Shared tests |
| Enforced `write=False` transactions | SQLite `query_only`; managed writes fail before SQL | Native read-only transaction proof |
| Uncertain commit/rollback handling | Fault-injected quarantine; close/reopen required | Shared state machine; configured proof tests |
| Declared relationships, foreign keys, duplicate pairs | Shared tests | Shared tests |
| Traversal, cycles, direction, budgets | Shared tests | Shared tests |
| Scalar JSON predicates, missing/null and ordered pagination | Shared fixture | Same fixture |
| Creation migrations | Shared tests | Shared tests |
| Constraint and index evolution | SQLite tests | Rejected before schema mutation |
| Raw SQL identity invariants | NOT NULL plus immutable-ID trigger | Primary key plus immutable-ID trigger |
| Physical backup | SQLite backup API | Unsupported |
| Logical import | SQLite restore fixtures | Mixed creation-only proof fixture |
| Structural check | Integrity/FK, generated structures, declared constraints and migration checksums | Metadata version, migration checksums and table existence only |
| External SQL | SQLite dialect and parameters; standalone explicit read intent | PostgreSQL dialect and Psycopg parameters; native read intent |
| Runtime settings | Effective SQLite version/journal/synchronous/FK report; explicit WAL/DELETE selection | Unsupported |
| Statistics and checkpoints | Explicit optimize/ANALYZE and structured WAL checkpoint results | Unsupported |

The matrix records implemented and tested examples, not exhaustive conformance.
In particular, PostgreSQL check() is not equivalent to SQLite's integrity check.
General PostgreSQL schema evolution and hosted cutover remain later milestones.

The managed physical format is now version 2: new record tables reject null
IDs and both backends enforce ID immutability. Old format-1 prototype files
are rejected at open rather than silently receiving the newer guarantees.
For disposable alpha fixtures, recreate the database. To preserve prototype
data, export it using the previous implementation and import that logical
artifact into a fresh database using this version. Logical artifact format 1
is unchanged. No automatic in-place physical upgrade is implemented.

Raw SQL does not acquire managed document version increments. Direct external
SQLite connections must enable foreign keys. Transactions have explicit
ownership; backends do not promise equal isolation or writer concurrency.

Standalone raw SQL remains write-capable by default. `write=False` selects an
enforced read transaction, while SQL issued through a transaction handle inherits
that transaction's mode. SQLite WAL qualification includes a two-connection proof
that a read transaction keeps a stable snapshot without reserving the writer slot.

A commit exception is not evidence that the transaction rolled back: the durable
outcome may be unknown. Failed commit, rollback, or required transaction-mode cleanup
quarantines the handle. Applications must close and reopen, inspect durable state,
and resolve operation identity before retrying. MeldDB does not reconnect or retry.

Writable WAL is additionally qualified against SQLite's WAL-reset fix. The current
policy accepts SQLite 3.51.3+, the 3.50.7 backport line, and the 3.44.6 backport line.
Other otherwise-compatible runtimes use DELETE for new files unless WAL is explicitly
requested, in which case open fails. This is a runtime policy, not PostgreSQL behavior.

## Run the proof

Start a disposable PostgreSQL 17 or 18 database. Set MELDDB_TEST_POSTGRES to
its connection string, then run:

```console
uv run --extra test --extra postgres pytest
```

The account needs permission to create and drop isolated test schemas.
Tests clean up their own schemas even when setup or assertions fail.
No PostgreSQL variable means SQLite-only tests; CI explicitly sets the variable
in separate PostgreSQL 17 and 18 jobs. The single shared core fixture runs
on both SQLite and the configured PostgreSQL server.

CI services follow the [GitHub service container documentation](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).
Connection ownership follows [Psycopg's connection API](https://www.psycopg.org/psycopg3/docs/api/connections.html).
