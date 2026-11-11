# Spec Delta

## ADDED Requirements

### Requirement: Pending constraints can be validated explicitly
The system SHALL expose constraint validation through a live write transaction, returning no data on success without committing or retrying. PostgreSQL SHALL force deferred constraints and constraint triggers and leave them immediate for the transaction. SQLite SHALL check foreign keys without changing constraint timing.

#### Scenario: Dry-run writes violate a deferred foreign key
- **WHEN** a caller validates after writing an unresolved deferred reference
- **THEN** validation fails before commit and the failed transaction must roll back

#### Scenario: PostgreSQL deferred application checks exist
- **WHEN** pending deferred uniqueness, exclusion or constraint-trigger checks fail
- **THEN** validation raises the translated constraint error and the transaction cannot continue

#### Scenario: Valid data is checked before intentional rollback
- **WHEN** validation succeeds and the caller subsequently raises an exception
- **THEN** the transaction rolls back all transactional effects without committing

#### Scenario: Validation is requested through an invalid scope
- **WHEN** a read-only, expired, failed or cross-thread transaction requests validation
- **THEN** ownership checks reject it before validation I/O and normal failure poisoning applies
