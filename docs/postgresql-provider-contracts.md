# PostgreSQL provider corrections

MeldStore's November 11, 2026 provider fixture at revision
`fa74f11efffc0ab182984e949c0d09fe1e9a1244` found transaction-control escapes and
misclassified disconnects (34 passed, 27 failed). The linked OpenSpec changes are
MeldDB `harden-postgresql-provider-contracts`, shared
`define-postgresql-provider-safety-contract`, and MeldStore
`add-postgresql-metadata-support` task 1.2.

## Public SQL boundary

Both `sql` and `sql_many` reject top-level transaction controls, including
punctuated commands such as `COMMIT;`, leading empty statements, and comments.
PostgreSQL recognizes nested block comments; SQLite ends a block comment at the
first closing delimiter. Validation happens before bulk parameter consumption;
failure poisons the transaction so earlier work cannot commit.

PostgreSQL also rejects `ABORT`, `START`, `SET`, `RESET`, `DISCARD`, `PREPARE`,
`EXECUTE`, and `DEALLOCATE` commands. Configure connections explicitly through
the provider instead of changing session state through application SQL. Driver
prepared execution is unchanged; these exclusions apply to submitted SQL commands.

Only the leading command is inspected. Application literals, identifiers,
routine bodies and native placeholders are passed unchanged to the driver.
Application triggers and DDL remain supported. The driver enforces one executable
statement; this guard is not an SQL authorization sandbox for untrusted routines,
extensions, or administrative privileges. Persistent mutation is still rejected
by the engine in read scopes; no SQL write-classification heuristic replaces it.

See [PostgreSQL lexical rules](https://www.postgresql.org/docs/17/sql-syntax-lexical.html)
and [transaction access modes](https://www.postgresql.org/docs/17/sql-set-transaction.html).

## Disconnect evidence

Connection SQLSTATEs, server shutdown, removed database, expired session and
SQLSTATE-less Psycopg operational/interface failures translate to `ConnectionError`.
Lock timeout, deadlock and serialization failure retain `BusyError`; constraint
errors retain their existing types. Translation retains the original driver cause.
See [Psycopg error types](https://www.psycopg.org/psycopg3/docs/api/errors.html).

This does not establish whether a disconnected transaction committed. Existing
structured begin/commit/rollback errors preserve phase, outcome and causes, and
quarantine the handle. Close, reopen and inspect durable application state before
retrying or cleaning up anything that transaction might reference. No automatic
retry or reconnection was added.

## Qualification boundary

SQLite remains supported. PostgreSQL remains experimental. The MeldStore provider
fixture is separate from its catalog, payload, transfer, backup and recovery gates.
The fixture uses only synthetic SQL data in a digest-pinned PostgreSQL 17 Docker
instance. No private Parquet data or application identifiers belong in this change.

Local verification on November 11, 2026, Python 3.13.15:

- Full upstream suite with SQLite and PostgreSQL 17.11: 603 passed, 23 skipped.
- Final focused control/error suite on both engines, including the additional
  carriage-return comment regression: 87 passed, 19 PostgreSQL-on-SQLite skips.
- Required `uv run --extra test pytest -q`: 375 passed, 22 skipped, with one
  pre-existing pytest-cache permission warning. `UV_FROZEN=true` preserved the lock.
- `uv run --extra test ruff check .`: passed (existing restricted-directory warnings).
- Strict owning-change validation and all seven canonical specs: passed.

The exact published revision and downstream live results are recorded in
MeldStore's `docs/postgresql-provider-verification.md` after consumer qualification.
