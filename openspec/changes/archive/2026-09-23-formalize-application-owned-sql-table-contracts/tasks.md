# Tasks

## 1. Mixed-Schema Contract Coverage

- [x] 1.1 Add a representative mixed-schema test fixture with managed data and application-owned tables, indexes, triggers, foreign keys, and junction rows; verify opening and managed migration preserve the application schema and `uv run --extra test pytest` passes for the focused tests
- [x] 1.2 Add inspection and structural-check assertions that distinguish managed and application-owned scope without claiming application-schema validation; verify the focused inspection tests pass on SQLite
- [x] 1.3 Add successful mixed managed/application transaction coverage and constraint-failure rollback coverage, including the poisoned-transaction rule; correct any contract violation exposed and verify the focused transaction tests pass
- [x] 1.4 Extend configured PostgreSQL proof tests for the portable mixed SQL/transaction subset, keep unsupported recovery behavior explicitly skipped or rejected, and verify the tests pass when `MELDDB_TEST_POSTGRES` is available while remaining cleanly skipped otherwise

## 2. Recovery Boundary Coverage

- [x] 2.1 Extend SQLite physical-backup tests to verify application-owned tables, rows, indexes, triggers, foreign keys, and junction relationships survive a live-database backup; verify the focused backup tests pass
- [x] 2.2 Extend logical-transfer tests to verify application-owned tables and native objects are reported as exclusions, the artifact is managed-only, and import does not recreate application schema or records; verify the focused transfer tests pass

## 3. User-Facing Contract Documentation

- [x] 3.1 Add a dedicated application-owned SQL guide defining ownership, migration responsibility, relationship boundaries, explicit mixed transactions, inspection limits, backend dialects, and recovery responsibilities; verify every example matches the tested public API
- [x] 3.2 Link the guide from the README and align the migration, inspection/recovery, logical-format, and backend-matrix documentation on physical-backup versus managed-logical-export semantics; verify local Markdown links resolve and terminology is consistent
- [x] 3.3 Document that managed physical mappings are diagnostic rather than stable foreign-key targets and that PostgreSQL remains experimental; verify no documentation promises a generic external-table migration framework or SQLite-equivalent PostgreSQL support

## 4. Qualification

- [x] 4.1 Run `uv run --extra test pytest` and verify the complete test suite passes
- [x] 4.2 Run `uv run --extra test ruff check .` and verify the repository passes lint checks
- [x] 4.3 Run strict OpenSpec validation for `formalize-application-owned-sql-table-contracts` and verify all proposal artifacts and capability deltas are valid
