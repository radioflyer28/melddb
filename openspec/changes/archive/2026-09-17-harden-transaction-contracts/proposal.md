## Why

MeldDB exposes read transactions and translates ordinary operation failures, but SQLite does not currently enforce `transaction(write=False)`, standalone raw SQL always selects a write transaction, and commit or rollback failures can leave connection state uncertain without preventing reuse. Consumers such as MeldStore therefore duplicate read classification and broken-connection handling that belong at the metadata-provider boundary.

## What Changes

- Enforce read-only transaction intent across managed operations and raw SQL on supported SQLite, while retaining PostgreSQL's native read-only transaction behavior as an experimental portability proof.
- Add an explicit read-only mode for standalone parameterized SQL so queries can avoid unnecessary writer reservation without exposing or parsing the underlying driver connection.
- Reject write operations through read-only database handles and read-only transactions with stable MeldDB errors before successful mutation.
- Quarantine a database handle after a failed commit or rollback when its transactional or durable state may be uncertain; only closing the handle remains valid.
- Preserve the initiating transaction failure as the primary error and retain cleanup failures through exception chaining or structured attributes instead of silently replacing the original cause.
- Add fault-injection and concurrency qualification for begin, operation, commit, rollback, read-only enforcement, and WAL reader/writer behavior.
- Document the recovery rule: close and reopen after an uncertain transaction outcome, then resolve application-level operation identity before retrying.
- **BREAKING**: operations that attempt writes inside `transaction(write=False)` will now fail, and a handle with an uncertain commit or failed rollback can no longer be reused.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `explicit-transactions`: Define enforceable read-only scopes, explicit standalone read SQL, and deterministic failure/quarantine behavior at transaction finalization boundaries.

## Impact

The public `Database.sql()` surface gains an additive read/write intent keyword, and the existing transaction contract becomes stricter. Transaction state, backend begin/finalization mechanics, stable error reporting, tests, documentation, and the SQLite/PostgreSQL capability matrix are affected. No third-party runtime dependency, retry policy, savepoint support, nested transaction support, pooling, async API, or blob-specific behavior is introduced. The shared `metadata-provider-contract` and MeldStore adapter tests must be reviewed before MeldStore updates its pinned MeldDB revision; repository-specific MeldStore adoption remains separate.
