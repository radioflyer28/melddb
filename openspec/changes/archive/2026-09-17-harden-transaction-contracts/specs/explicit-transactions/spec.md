# Spec Delta

## MODIFIED Requirements

### Requirement: Explicit atomic transaction scope
The system SHALL provide a caller-owned transaction scope that atomically commits all successful operations, SHALL roll back the scope when an exception escapes, and SHALL fail closed when transaction start or finalization cannot establish a reusable connection state.

#### Scenario: Related writes commit together
- **WHEN** a caller completes multiple writes through one transaction-owned handle
- **THEN** all writes become durable in one commit

#### Scenario: Exception rolls back the scope
- **WHEN** an exception exits an active transaction scope and rollback succeeds
- **THEN** none of that scope's writes are committed and the initiating exception escapes unchanged

#### Scenario: Transaction start fails
- **WHEN** the backend cannot begin the requested transaction
- **THEN** no transaction-owned handle is yielded and the database handle remains reusable only if MeldDB can establish that no transaction remains active

#### Scenario: Commit outcome is uncertain
- **WHEN** commit raises before MeldDB can confirm whether the transaction became durable
- **THEN** the system reports an uncertain commit outcome and rejects further operations through that database handle until it is closed

#### Scenario: Rollback cannot be confirmed
- **WHEN** rollback raises while handling an operation or application failure
- **THEN** the system reports the rollback failure, preserves the initiating failure for inspection, and rejects further operations through that database handle until it is closed

### Requirement: Raw SQL remains explicit
The system SHALL support parameterized driver-dialect SQL within standalone or explicit transaction scopes, SHALL let standalone calls declare read-only intent without changing the default write-capable behavior, and SHALL reject transaction-control SQL through that interface.

#### Scenario: Application table participates in transaction
- **WHEN** a caller writes an application-owned SQL table through a write transaction handle alongside managed data
- **THEN** both sets of changes share the same commit or rollback outcome

#### Scenario: Transaction-control statement is submitted
- **WHEN** a caller submits BEGIN, COMMIT, ROLLBACK, SAVEPOINT, or equivalent transaction control through raw SQL
- **THEN** the system rejects it and directs ownership to the transaction interface

#### Scenario: Standalone SQL declares read-only intent
- **WHEN** a caller executes parameterized SQL with standalone read-only intent
- **THEN** the statement runs in an enforced read-only transaction and does not reserve a writer where the supported backend provides concurrent reader/writer operation

#### Scenario: Standalone SQL omits intent
- **WHEN** a caller invokes standalone SQL without a read-only declaration
- **THEN** the existing write-capable transaction behavior is preserved for compatibility

## ADDED Requirements

### Requirement: Declared read-only scopes are enforced
The system MUST enforce read-only database handles and `write=False` transaction scopes for both managed operations and raw SQL without relying on caller-supplied SQL classification.

#### Scenario: Managed write is attempted in a read transaction
- **WHEN** a caller invokes a managed write through a `write=False` transaction
- **THEN** the operation is rejected before mutation and the failed transaction cannot commit

#### Scenario: Raw SQL mutation is attempted in a read transaction
- **WHEN** raw SQL attempts to change persistent state through a `write=False` transaction
- **THEN** the backend rejects the mutation, no change is committed, and the failed transaction cannot continue

#### Scenario: Write is attempted through a read-only database
- **WHEN** a caller requests a write transaction or managed write through a database opened read-only
- **THEN** the system rejects the request before a successful mutation and keeps the database contents unchanged

#### Scenario: Portable read-only behavior is exercised
- **WHEN** the same read-only transaction scenarios run on supported SQLite and the experimental PostgreSQL adapter
- **THEN** both reject mutations and preserve data, while backend-specific transaction mechanics remain private

### Requirement: Uncertain connections are quarantined
The system MUST mark a database handle unusable when transaction finalization or required read-only-state cleanup fails, MUST reject all later operations other than close, and MUST NOT reconnect or retry automatically.

#### Scenario: Operation follows uncertain finalization
- **WHEN** a caller invokes a query, mutation, transaction, maintenance, inspection, backup, export, or import through a quarantined handle
- **THEN** the operation fails without database I/O and directs the caller to close and reopen

#### Scenario: Quarantined handle is closed
- **WHEN** a caller closes a quarantined database handle
- **THEN** MeldDB attempts to release the underlying connection without requiring another database operation

#### Scenario: Caller resolves an uncertain commit
- **WHEN** an application receives an uncertain commit outcome
- **THEN** recovery requires reopening and inspecting durable application state before deciding whether an idempotent operation may be retried

### Requirement: Transaction outcome errors preserve evidence
The system SHALL expose stable MeldDB transaction-finalization errors and SHALL retain the underlying commit, rollback, and initiating operation failures for programmatic inspection.

#### Scenario: Commit raises
- **WHEN** the backend commit operation raises
- **THEN** MeldDB raises a stable commit outcome error whose cause retains the backend failure

#### Scenario: Rollback raises after another failure
- **WHEN** rollback raises while another exception is already escaping the transaction
- **THEN** MeldDB raises a stable rollback outcome error that retains both the initiating exception and the rollback failure

#### Scenario: Rollback succeeds after another failure
- **WHEN** rollback succeeds while another exception is escaping the transaction
- **THEN** MeldDB re-raises the initiating exception without wrapping it in a transaction-finalization error
