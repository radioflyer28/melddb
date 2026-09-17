# Spec Delta

## Purpose

Defines explicit connection and transaction ownership so application persistence remains visible, composable, and predictable.

## ADDED Requirements

### Requirement: Explicit atomic transaction scope
The system SHALL provide a caller-owned transaction scope that atomically commits all successful operations and rolls back the scope when an exception escapes.

#### Scenario: Related writes commit together
- **WHEN** a caller completes multiple writes through one transaction-owned handle
- **THEN** all writes become durable in one commit

#### Scenario: Exception rolls back the scope
- **WHEN** an exception exits an active transaction scope
- **THEN** none of that scope's writes are committed

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
The system SHALL support parameterized driver-dialect SQL within standalone or explicit transaction scopes while rejecting transaction-control SQL through that interface.

#### Scenario: Application table participates in transaction
- **WHEN** a caller writes an application-owned SQL table through a transaction handle alongside managed data
- **THEN** both sets of changes share the same commit or rollback outcome

#### Scenario: Transaction-control statement is submitted
- **WHEN** a caller submits BEGIN, COMMIT, ROLLBACK, SAVEPOINT, or equivalent transaction control through raw SQL
- **THEN** the system rejects it and directs ownership to the transaction interface
