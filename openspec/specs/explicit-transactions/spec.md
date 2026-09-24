# explicit-transactions Specification

## Purpose
Defines explicit connection and transaction ownership so application persistence remains visible, composable, and predictable.

## Requirements

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

### Requirement: Transaction handles enforce ownership
The system SHALL reject nested transactions, use of an expired transaction handle, ordinary database operations while a transaction is active, and use of a database handle from a thread other than its creator.

#### Scenario: Database handle used inside transaction
- **WHEN** a caller invokes a database-owned operation while its explicit transaction is active
- **THEN** the operation fails and the transaction cannot commit

#### Scenario: Handle crosses a thread
- **WHEN** a database handle is used outside its creating thread
- **THEN** the system rejects the operation without performing database I/O

### Requirement: Failed transactions cannot continue
The system MUST mark an explicit transaction unusable after any operation in that transaction fails, even if application code catches the operation error inside the scope.

#### Scenario: Caught operation error
- **WHEN** an operation fails and its exception is caught before leaving the transaction block
- **THEN** a later operation or commit is rejected and the transaction rolls back

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

### Requirement: Bulk SQL remains transaction-owned and explicit
The system SHALL provide bulk parameterized SQL only through a live
transaction-owned handle, SHALL execute one statement against an ordered,
single-pass iterable of parameter sets, and SHALL return a plain completion
summary containing the number of submitted parameter sets and the affected-row
count when the backend reports one. It MUST NOT create, commit, retry, split, or
continue a transaction implicitly.

#### Scenario: Non-empty bulk execution succeeds
- **WHEN** a caller supplies a non-result-producing statement and multiple valid parameter sets through a live write transaction
- **THEN** the system executes them in input order and returns their submitted count plus the backend's affected-row count or an explicit unavailable value

#### Scenario: Empty bulk input is supplied
- **WHEN** a caller supplies an empty parameter-set iterable through a live write transaction
- **THEN** the system returns zero submitted and zero affected rows without executing the SQL statement

#### Scenario: Bulk SQL is requested outside its owner
- **WHEN** a caller attempts bulk SQL through an expired handle, a handle from another thread, or the database handle while a transaction is active
- **THEN** the system rejects the operation under the existing ownership rules without executing the statement

#### Scenario: Bulk mutation is requested in a read transaction
- **WHEN** a caller requests bulk SQL through a read-only transaction
- **THEN** the system rejects the operation before consuming parameter sets or performing database I/O and the failed transaction cannot commit

### Requirement: Bulk SQL fails closed as one transaction operation
The system MUST mark the transaction unusable when statement validation,
parameter iteration, parameter binding, backend execution, result-boundary
validation, or database constraints fail during bulk SQL. It MUST preserve the
existing translated error boundary and MUST NOT report partial success or retry
any parameter set automatically.

#### Scenario: Parameter iteration fails
- **WHEN** the parameter iterable raises after yielding one or more parameter sets
- **THEN** the operation error escapes, the transaction cannot continue, and rollback removes any changes already attempted by the bulk operation

#### Scenario: Caller catches a bulk operation error
- **WHEN** a caller catches a binding, constraint, or driver error inside the transaction block
- **THEN** a later operation or commit is rejected and the complete transaction rolls back

#### Scenario: Result-producing statement is supplied
- **WHEN** a bulk statement produces rows, including through a returning clause
- **THEN** the system rejects the unsupported result boundary, exposes no partial result set, and the failed transaction cannot commit

#### Scenario: Transaction-control statement is supplied
- **WHEN** a caller submits transaction or connection-control SQL through bulk execution
- **THEN** the system rejects it under the same ownership boundary as ordinary raw SQL without delegating transaction control to the statement

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
