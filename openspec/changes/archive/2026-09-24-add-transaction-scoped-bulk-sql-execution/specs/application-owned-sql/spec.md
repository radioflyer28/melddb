# Spec Delta

## ADDED Requirements

### Requirement: Application SQL supports explicit bulk composition
The system SHALL allow a caller to apply one parameterized, driver-dialect SQL
statement to multiple parameter sets through an existing caller-owned write
transaction, SHALL compose that bulk work atomically with managed operations and
ordinary application SQL in the same scope, and MUST NOT adopt or infer the
application-owned schema involved.

#### Scenario: Bulk application rows and managed work commit together
- **WHEN** a caller successfully executes bulk application-owned inserts and managed writes through one write transaction
- **THEN** every bulk row and managed change becomes durable in the transaction's single commit

#### Scenario: A bulk application row violates a constraint
- **WHEN** any parameter set violates an application-owned foreign key, uniqueness rule, check, or trigger
- **THEN** the transaction becomes unusable and rolls back every earlier bulk, ordinary SQL, and managed change in that scope

#### Scenario: Application uses backend-dialect parameters
- **WHEN** a caller executes the same logical bulk workflow on SQLite or the experimental PostgreSQL adapter
- **THEN** the caller supplies that backend's SQL and parameter dialect while observing the same transaction ownership and rollback behavior
