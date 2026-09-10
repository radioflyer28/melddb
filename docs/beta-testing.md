# Controlled beta testing

MeldDB 0.1.0rc1 is ready for deliberate user evaluation, not a supported release.
Gate C remains open for macOS Python 3.12-3.14 qualification. Existing evidence
covers Windows/Linux Python 3.12-3.14; PostgreSQL 17/18 remains an experimental
portability proof. See [qualification](release-qualification.md) for exact runtime
versions and artifact hashes and [the matrix](backend-matrix.md) for backend limits.

## Start with one real workflow

Follow [the README](../README.md) to install from a checkout or a provided wheel.
There is no published package or public issue tracker configured for this local
repository. Record which artifact or Git revision you used. Documentation in a
newer checkout may differ from the README bundled in an older wheel/sdist.

Start with reproducible or backed-up data and one bounded application workload:

- Settings/documents: store, query, replace conditionally, and reopen.
- Address book: scalar types, projections, partial row updates, and migrations.
- Package dependencies: mixed transactions, links, and bounded traversal.
- Activity records: batched writes, explicit retention, and workload-sized queries.

Run the examples in fresh directories. Then try your application's actual data,
including unusual metadata keys and concurrent handles if relevant. A successful
example is not a substitute for checking the records your application expects.

## Preserve a recovery path

Use `melddb backup source.db fresh-backup.db` for SQLite physical backup; do not
copy an active WAL database file. Open the resulting database, run `check()`, and
verify application records before relying on it. Use logical export/import for
managed-data transfer into a new or empty destination; external tables are excluded.
See [physical recovery](inspection-and-recovery.md) and
[logical recovery](logical-format.md). Keep the original until restoration is verified.

A database backup does not include external blob files or S3 objects managed by a
consumer. That consumer must coordinate its own full-data backup and recovery.

## Known boundaries to test against

- Required SQLite JSON behavior is checked at open. A version >=3.38 alone does
  not guarantee compatibility; include the loaded SQLite version in reports.
- Documents replace their whole body; query results are detached and paginated.
- Transactions have exclusive ownership and are poisoned by failed operations.
  Connections are thread-confined; there are no automatic transaction retries.
- Raw SQL uses backend syntax and does not acquire managed version increments.
- Migrations support a small explicit operation set; automatic schema diffing,
  renames, drops, and arbitrary data conversion are not provided.
- PostgreSQL's supported proof subset does not establish full SQLite parity.
- No async API, synchronization, libSQL adapter, or production TypeScript SDK.

## Useful feedback

Send reports through the project maintainer's agreed channel. Include:

1. MeldDB version and wheel hash or Git commit; OS, Python, and loaded SQLite
   version (or PostgreSQL/Psycopg versions for that experimental backend).
2. A small reproducer, expected behavior, actual result, and complete exception
   chain. Remove passwords, connection credentials, and private application data.
3. Relevant migrations, transaction boundaries, and whether multiple processes or
   threads use separate handles. Note direct SQL writes when they are involved.
4. For performance: record/edge counts, query shape, indexes, batch size, timings,
   and whether storage is local or remote. Compare equivalent work and guarantees.
5. For usability: the helper code you had to write, unclear errors, or why you
   needed raw SQL. Repeated friction is especially useful evidence for API changes.

Prioritize reproducible correctness/recovery problems, then repeated API friction
and measured regressions. Beta feedback should inform full PostgreSQL work before
expanding into more backends or abstractions. Feature development remains paused
until requested; beta preparation does not close release gates or publish artifacts.
