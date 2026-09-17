# schema-evolution Specification

## Purpose
Defines explicit, ordered schema creation and evolution with repeatability, checksum protection, and transactional failure behavior.

## Requirements

### Requirement: Ordered immutable migrations
The system SHALL identify migrations by caller-supplied ordered IDs, treat exact reapplication as idempotent, and reject reuse of an applied ID with different operations.

#### Scenario: Exact migration is reapplied
- **WHEN** an already applied migration with the same checksum and operations is submitted
- **THEN** the system reports success without changing schema or data

#### Scenario: Migration ID is changed
- **WHEN** an applied migration ID is submitted with different operations
- **THEN** the system rejects it before applying the conflicting revision

### Requirement: Migration failure is atomic
The system SHALL apply each migration transactionally and SHALL preserve the pre-migration schema and data when validation or execution fails.

#### Scenario: Constraint evolution fails validation
- **WHEN** existing data violates a proposed supported constraint change
- **THEN** the migration fails without recording its ID or leaving partial schema changes

### Requirement: Backend capability differences are explicit
The system SHALL reject unsupported schema evolution before mutation and SHALL document PostgreSQL evolution as experimental until it reaches the published capability contract.

#### Scenario: Unsupported PostgreSQL evolution is requested
- **WHEN** a migration contains an evolution operation outside the PostgreSQL proof subset
- **THEN** the system raises an unsupported-operation error before changing the schema

### Requirement: Direct SQL invariants survive migration
The system SHALL preserve declared managed constraints and identity invariants for writes performed through ordinary SQL where the documented backend contract supports them.

#### Scenario: Direct SQL changes immutable ID
- **WHEN** a SQL writer attempts to mutate a managed row's immutable identity
- **THEN** the database rejects the change
