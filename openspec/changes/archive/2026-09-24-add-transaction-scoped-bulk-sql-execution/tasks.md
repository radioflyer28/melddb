# Tasks

## 1. Public transaction contract

- [x] 1.1 Add `Transaction.sql_many(statement, parameter_sets)` at the existing
  raw-SQL ownership boundary, with no `Database.sql_many` convenience. Verify
  focused tests cover live, expired, wrong-thread, and database-handle ownership.
- [x] 1.2 Implement ordered, single-pass parameter consumption and the plain
  `parameter_sets`/`affected_rows` completion summary without eager batch
  materialization. Verify empty input returns both counts as zero without backend
  execution and a generator is consumed only once.
- [x] 1.3 Apply write intent and statement-control validation before consuming the
  parameter iterable. Verify read-only and transaction-control rejection preserve
  the existing fail-closed transaction behavior.

## 2. Backend bulk execution

- [x] 2.1 Add a backend bulk-execution seam and implement SQLite using native
  parameter binding and `executemany`, normalizing negative or unavailable aggregate
  row counts to `None`. Verify binding, constraint, and driver failures use existing
  MeldDB error translation.
- [x] 2.2 Implement the experimental PostgreSQL adapter through its native bulk
  execution mechanics and parameter dialect. Verify configured PostgreSQL 17 and 18
  runs observe the same public completion and rollback contract as SQLite.
- [x] 2.3 Detect result-producing bulk statements after driver execution without
  exposing or silently discarding rows. Verify `SELECT` and DML with `RETURNING`
  poison the transaction and roll back all attempted work on both configured
  backends.

## 3. Transaction conformance

- [x] 3.1 Add SQLite conformance tests for ordered application-owned inserts,
  composition with managed and ordinary SQL work, empty batches, known and unknown
  affected-row counts, and a large generator. Verify successful work becomes durable
  only at the surrounding transaction commit.
- [x] 3.2 Add fail-closed tests for iteration, binding, constraint, driver, and
  result-boundary failures, including errors caught inside the transaction block.
  Verify no partial rows become durable and the poisoned transaction cannot continue
  or commit.
- [x] 3.3 Parameterize portable bulk scenarios for the PostgreSQL proof suite while
  retaining the documented experimental status. Verify the existing CI command
  `uv run --extra test --extra postgres pytest` passes against PostgreSQL 17 and 18
  when `MELDDB_TEST_POSTGRES` is configured.

## 4. Documentation and performance evidence

- [x] 4.1 Document the `sql_many` signature, completion summary, backend SQL dialect,
  explicit transaction requirement, generator behavior, caller-owned chunking, and
  unsupported result rows/per-row statuses. Verify the documentation includes an
  executable application-owned-table example.
- [x] 4.2 Add a reproducible benchmark comparing row-by-row `Transaction.sql`,
  `Transaction.sql_many`, and direct-driver `executemany`. Verify it records workload,
  environment, SQL call counts, and result correctness and labels timings as local
  evidence rather than universal guarantees.
- [x] 4.3 Update the backend capability/qualification documentation and record that
  the shared metadata-provider responsibility boundary is unchanged. Verify any
  MeldStore adoption remains explicitly assigned to that repository and release
  cycle.

## 5. Final verification

- [x] 5.1 Run `uv run --extra test pytest` and verify the full supported SQLite test
  suite passes.
- [x] 5.2 With PostgreSQL 17 and 18 configured in turn, run
  `uv run --extra test --extra postgres pytest` and verify the portability-proof
  suite passes for both versions.
- [x] 5.3 Run `uv run --extra test ruff check .` and verify the repository is clean.
- [x] 5.4 Run strict OpenSpec validation for
  `add-transaction-scoped-bulk-sql-execution` and verify every artifact and delta
  scenario is accepted.
