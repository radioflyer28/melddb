## Context

See `proposal.md` for motivation and `specs/explicit-transactions/spec.md` for the behavioral contract. MeldDB currently routes standalone operations through `Database.transaction()`, marks an explicit transaction failed after an operation error, and translates driver exceptions. The transaction object does not retain its declared write mode, SQLite read transactions use an ordinary deferred `BEGIN`, raw SQL always requests a write transaction, and commit/rollback cleanup has no database-handle quarantine state.

MeldStore independently compensates with a partial SQL classifier and a broken-catalog state. That duplication is evidence for a narrow upstream contract, but MeldDB must remain generic and must not absorb blob lifecycle concepts.

## Goals / Non-Goals

**Goals:**

- Make declared read-only intent an enforced transaction property rather than a naming convention.
- Keep standalone reads explicit without changing the compatibility default for raw SQL.
- Represent transaction lifecycle and uncertain outcomes consistently above both adapters.
- Preserve enough error evidence for an application to distinguish a normal rollback from an outcome that requires reopen-and-resolve recovery.
- Let MeldStore remove its MeldDB-side SQL classifier and broken-connection policy after separate adapter qualification.

**Non-Goals:**

- Parsing or proving the semantics of arbitrary SQL text.
- Automatic retries, reconnects, idempotency keys, or commit-outcome resolution.
- Nested transactions, savepoints, pooling, asynchronous connections, or configurable isolation levels.
- General PostgreSQL qualification beyond exercising this contract as an experimental portability proof.
- Changes to MeldStore implementation or the shared cross-repository store in this change.

## Decisions

### Put transaction lifecycle in one fail-closed state machine

`Database` will distinguish idle, active, and quarantined states. A transaction will retain its declared write mode and remain live only while it is the database's active transaction.

```text
IDLE -- begin succeeds --> ACTIVE_READ or ACTIVE_WRITE
  ^                              |
  |                              +-- commit confirmed --------+
  |                              +-- rollback confirmed -------+
  |                                                           |
  +-----------------------------------------------------------+

ACTIVE_* -- uncertain begin/finalization/cleanup --> QUARANTINED
QUARANTINED -- close --> CLOSED
```

Ordinary operation failures continue to poison only the active transaction. A successful rollback returns the database to idle and re-raises the initiating error unchanged. A commit failure, rollback failure, or required mode-cleanup failure that prevents MeldDB from establishing a safe reusable state moves the database to quarantined. All public operations except idempotent close reject before database I/O in that state.

This is preferred to optimistic reuse because a lost commit acknowledgement can represent either durable or non-durable state. Automatic reconnection is rejected because it would hide connection ownership and could encourage an unsafe retry.

### Enforce read-only intent at both managed and backend boundaries

The transaction object will store `write`. Managed mutation paths already identify themselves through `_operation(write=True)`; the transaction scope will reject those calls before SQL when its mode is read-only. This gives deterministic errors for MeldDB-managed writes.

Raw SQL will rely on backend enforcement rather than a statement classifier. SQLite read transactions will activate and verify `PRAGMA query_only`, begin a deferred transaction, and restore the prior query-only state during finalization. PostgreSQL will continue to use a native `READ ONLY` transaction. Existing rejection of transaction/connection-control SQL remains a separate ownership safeguard, not a read/write parser.

SQLite's query-only setting is connection-scoped, so activation, transaction start, commit/rollback, and restoration belong to one backend-owned lifecycle. Failure to restore the prior state quarantines the handle. This is preferred to keyword allowlisting because writable common-table expressions, triggers, user-defined functions, and future SQL syntax make text classification incomplete.

For a database opened with `readonly=True`, the shared database layer rejects write transactions and managed writes before yielding a transaction. SQLite's read-only URI remains defense in depth; PostgreSQL automatic and explicit transactions use read-only mode even though PostgreSQL support remains experimental.

### Make standalone SQL intent explicit without burdening transaction SQL

`Database.sql(statement, params=(), *, write=True)` gains a keyword-only Boolean. The default remains `True` so existing DDL, DML, and mixed application SQL continue to work. Passing `write=False` opens one enforced read-only transaction, allowing SQLite WAL readers to avoid `BEGIN IMMEDIATE` writer reservation.

`Transaction.sql(statement, params=())` inherits the mode selected by `Database.transaction(write=...)` and does not require a redundant flag. A read transaction can execute arbitrary driver-dialect queries, while any attempted mutation is rejected by backend read-only enforcement and poisons the transaction under the existing failure rule.

Separate `query()` and `execute()` methods were considered but rejected for this change: they would duplicate the existing escape hatch and still could not infer whether arbitrary SQL is read-only. A Boolean on transaction-owned SQL was also rejected because it could conflict with the enclosing transaction's declared mode.

### Add structured finalization errors while retaining underlying evidence

Add a transaction-finalization error family under `TransactionError`, with stable error codes and plain attributes describing `phase` and known `outcome`. A commit failure reports an unknown outcome and retains the backend exception as its cause. A rollback failure retains both the initiating exception and the rollback/cleanup exception for programmatic inspection. If rollback succeeds, no finalization wrapper is introduced.

The exact subclasses should distinguish commit failure from rollback/cleanup failure so consumers do not need to parse messages. The implementation will keep attributes detached from backend connections and avoid exposing driver objects except as ordinary exception evidence.

Exception groups were considered but rejected as the primary API because callers usually need one recovery decision: the handle is quarantined and durable state must be resolved. Silently preferring the rollback exception was also rejected because it discards the application or operation failure that initiated cleanup.

### Treat begin failures according to established connection state

A failure before a transaction handle is yielded does not create an active public transaction. The adapter will perform backend-appropriate state inspection or cleanup. Known failures that leave the connection idle, such as an SQLite writer reservation conflict, remain ordinary translated errors and permit reuse. If MeldDB cannot establish an idle connection, it quarantines the handle.

This avoids quarantining healthy SQLite connections after expected `BUSY` results while retaining fail-closed behavior for transport failures or partially entered transactions.

### Qualify concurrency and recovery behavior at public boundaries

Tests will exercise managed and raw-SQL writes in read scopes, standalone read SQL, read-only database handles, caught errors, deferred constraint failures at commit, injected rollback/cleanup failures, and attempts to reuse quarantined handles. A two-connection WAL test will verify that an active SQLite read transaction does not reserve the single writer slot. PostgreSQL tests run only when configured and establish portability evidence rather than supported-backend status.

Crash tests continue to define the durable commit boundary. Fault injection complements them by checking behavior when Python receives an exception but cannot infer whether the backend committed.

## Risks / Trade-offs

- **SQLite query-only state can leak if lifecycle cleanup is incomplete** -> Keep activation and restoration adapter-owned, verify effective state, and quarantine on failed restoration.
- **A commit error can occur even when the commit became durable** -> Never claim rollback or retry safety; require close, reopen, and application-level resolution.
- **Conservative quarantine can require reopening after a recoverable driver failure** -> Prefer safety over reuse only at uncertain finalization boundaries; expected begin conflicts remain reusable when idle state is established.
- **Existing callers may mutate inside `write=False` transactions** -> Treat this as a documented behavioral correction and direct those callers to an explicit write transaction.
- **Adding structured error classes expands the public API** -> Keep the hierarchy small, stable, dependency-free, and focused on recovery decisions.
- **PostgreSQL transaction status differs from SQLite** -> Keep state inspection and read-only mechanics in adapters and qualify PostgreSQL separately without claiming full parity.

## Migration Plan

1. Add failing contract tests for enforced read scopes, standalone read SQL, finalization failures, quarantine, and WAL reader/writer concurrency.
2. Add transaction mode and quarantine state plus structured finalization errors in shared connection ownership code.
3. Implement backend-specific read-only activation, begin-state recovery, and finalization cleanup for SQLite and PostgreSQL.
4. Update public documentation and the backend matrix with read-only, uncertainty, and reopen-and-resolve guidance.
5. Review the shared `metadata-provider-contract` and run MeldStore's adapter tests before a separate MeldStore change removes duplicated safeguards or advances its pinned MeldDB revision.
6. Run the complete uv-managed test and Ruff suites, plus configured PostgreSQL qualification when available.

Rollback can remove the additive standalone SQL keyword and error classes, but callers migrated to enforced read transactions must explicitly return to write transactions before downgrading. No database-format or data migration is required.
