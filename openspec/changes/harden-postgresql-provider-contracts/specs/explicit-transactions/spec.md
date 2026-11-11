# Spec Delta

## ADDED Requirements

### Requirement: SQL controls cannot escape caller ownership
MeldDB SHALL reject top-level transaction and connection-control commands through raw and bulk SQL before executing them. Rejection MUST account for command delimiters, leading empty statements and the selected backend's comment syntax, and MUST poison the caller-owned transaction without consuming bulk parameters.

#### Scenario: Control command has punctuation or comments
- **WHEN** a caller submits a transaction control such as `COMMIT;` or a comment-prefixed control
- **THEN** it is rejected before execution and preceding writes roll back even if the caller catches the error

#### Scenario: PostgreSQL session control is submitted
- **WHEN** raw or bulk SQL submits SET, RESET, DISCARD, START, ABORT, PREPARE, EXECUTE or DEALLOCATE commands
- **THEN** MeldDB rejects them through the public SQL boundary and does not upgrade a read-only scope or change session configuration

#### Scenario: Ordinary SQL contains control-like text
- **WHEN** supported application SQL contains control words, semicolons or comment markers inside literals, identifiers or routine bodies
- **THEN** the statement and native parameter bindings retain their driver semantics without textual rewriting

### Requirement: PostgreSQL disconnects preserve connection failure classification
MeldDB SHALL classify PostgreSQL connection-loss, shutdown and expired-session errors as ConnectionError, including driver operational or interface failures without a SQLSTATE. Constraint and concurrency failures MUST retain their existing classifications, and translated errors MUST preserve the driver cause.

#### Scenario: Session termination interrupts an operation
- **WHEN** the server terminates the connection and rollback also fails on the closed connection
- **THEN** the structured rollback outcome retains connection errors for both failures, reports an unknown outcome and quarantines the handle without automatic retry

#### Scenario: Concurrency failure remains recoverable by the caller
- **WHEN** PostgreSQL reports a lock timeout, deadlock or serialization failure
- **THEN** the operation retains BusyError classification rather than becoming a connection failure
