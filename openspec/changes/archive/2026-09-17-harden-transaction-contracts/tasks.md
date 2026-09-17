## 1. Read-Only Contract Tests

- [x] 1.1 Add failing tests for managed writes attempted through `transaction(write=False)` and `open(..., readonly=True)`; verify rejection occurs before mutation, poisons an active transaction, and preserves stored data.
- [x] 1.2 Add failing raw-SQL tests for arbitrary SQLite and PostgreSQL mutations inside read transactions, including writable CTE or trigger-mediated cases where supported; verify enforcement does not depend on a SELECT-only SQL classifier.
- [x] 1.3 Add failing tests for `Database.sql(..., write=False)`, Boolean argument validation, the existing write-capable default, and `Transaction.sql()` inheriting its enclosing mode; verify legacy standalone DDL/DML remains compatible.
- [x] 1.4 Add a two-connection SQLite WAL test showing an active standalone or explicit read transaction does not reserve the writer slot while retaining a stable read snapshot.

## 2. Failure and Quarantine Tests

- [x] 2.1 Add begin-failure fault tests that distinguish a known idle SQLite busy result from an uncertain or partially entered transaction; verify only the uncertain case quarantines the database handle.
- [x] 2.2 Add commit-failure tests, including deferred constraints and injected lost acknowledgements before and after durable commit; verify the error reports unknown outcome, retains its backend cause, and prevents handle reuse.
- [x] 2.3 Add rollback and read-mode-cleanup failure tests; verify the finalization error retains both the initiating and cleanup failures and that successful rollback still re-raises the initiating exception unchanged.
- [x] 2.4 Add parametrized tests covering every public database operation after quarantine plus idempotent close; verify rejected operations perform no database I/O and close remains available.

## 3. Transaction State and Errors

- [x] 3.1 Add the minimal stable transaction-finalization error hierarchy and plain `phase`, `outcome`, initiating-error, and backend-error evidence; verify error codes, attributes, and exception causes without exposing connection objects.
- [x] 3.2 Add explicit idle, active, quarantined, and closed connection-state checks to `Database`; verify existing ownership, thread confinement, nested-transaction rejection, and expired-handle behavior remain intact.
- [x] 3.3 Store and validate transaction write mode, reject managed mutations from read scopes before SQL, and make close bypass quarantine while retaining owner-thread safety; verify focused ownership and poisoning tests pass.
- [x] 3.4 Refactor transaction entry and exit so confirmed rollback restores idle state, uncertain begin/finalization quarantines, and commit failures are never represented as confirmed rollback; verify the failure tests from section 2 pass.

## 4. Backend Read-Only Mechanics and SQL API

- [x] 4.1 Implement `Database.sql(statement, params=(), *, write=True)` while keeping `Transaction.sql(statement, params=())` mode-inheriting; verify standalone read SQL uses a read transaction and existing callers remain source-compatible.
- [x] 4.2 Implement adapter-owned SQLite query-only activation, verification, deferred begin, prior-state restoration, and transaction-state inspection; verify raw mutations fail, expected busy begins remain reusable, and cleanup failures quarantine.
- [x] 4.3 Implement or complete PostgreSQL read-only-handle and transaction enforcement using native transaction characteristics; verify the shared read-only contract passes when `MELDDB_TEST_POSTGRES` is configured without upgrading PostgreSQL's experimental status.
- [x] 4.4 Ensure maintenance and other non-transactional SQLite operations establish the required writable connection mode and honor quarantine/read-only checks; verify runtime-management tests remain deterministic after preceding read transactions.

## 5. Documentation and Consumer Boundary

- [x] 5.1 Update README transaction and raw-SQL examples with enforced read scopes, standalone `write=False`, compatibility defaults, and close/reopen/resolve guidance; verify examples use only public APIs.
- [x] 5.2 Update the backend matrix and validation evidence to distinguish supported SQLite behavior from experimental PostgreSQL proof, including WAL reader/writer qualification and uncertain finalization semantics.
- [x] 5.3 Review the shared `metadata-provider-contract` against the implemented API and record whether a separate shared-store delta is required; verify this MeldDB change does not modify MeldStore code or absorb blob-specific behavior.
- [x] 5.4 Document the downstream MeldStore adapter qualification needed before removing its SQL classifier, broken-catalog state, or advancing its pinned MeldDB revision; verify those adoption steps remain outside this change.

## 6. Verification

- [x] 6.1 Run `uv run --extra test pytest` and verify the complete supported SQLite suite passes, including existing crash, backup, migration, raw-SQL, and runtime-management coverage.
- [x] 6.2 When PostgreSQL qualification is configured, run `uv run --extra test --extra postgres pytest` and verify read-only and transaction-finalization proof tests pass without claiming full backend support.
- [x] 6.3 Run `uv run --extra test ruff check .` and verify the dependency-free core and supported Python-version constraints remain satisfied.
- [x] 6.4 Run strict OpenSpec validation for `harden-transaction-contracts` and verify the implementation, documentation, delta spec, and completed task evidence agree.
