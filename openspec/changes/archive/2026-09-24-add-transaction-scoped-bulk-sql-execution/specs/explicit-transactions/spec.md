# Spec Delta

## ADDED Requirements

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
