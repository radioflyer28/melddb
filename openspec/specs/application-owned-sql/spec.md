# application-owned-sql Specification

## Purpose
Defines how ordinary application-owned SQL schemas coexist and compose with MeldDB-managed data without transferring schema ownership or hiding database I/O.

## Requirements

### Requirement: Application-owned SQL objects coexist without adoption
The system SHALL preserve application-owned SQL tables and native objects in the same database as managed data and MUST NOT adopt, rename, rewrite, or drop them as a side effect of managed initialization or migration.

#### Scenario: Existing application database gains managed data
- **WHEN** a caller opens a database containing application-owned tables and then creates managed objects
- **THEN** the application-owned schema and records remain unchanged and accessible through explicit SQL

#### Scenario: Managed facade is requested for an application table
- **WHEN** a caller requests a managed object handle using the name of an application-owned table
- **THEN** the system does not infer or adopt that table's schema as a managed declaration

### Requirement: Application retains schema and migration ownership
The system SHALL leave application-owned DDL, migration ordering and history, indexes, triggers, constraints, compatibility policy, and schema validation under application control and SHALL NOT represent managed migrations as coverage for those objects.

#### Scenario: Application schema changes
- **WHEN** an application-owned table or native object must evolve
- **THEN** the application supplies and records that evolution explicitly rather than relying on a MeldDB managed migration

#### Scenario: Application schema is structurally valid for the database but wrong for the application
- **WHEN** a structural check encounters no native integrity or foreign-key violation in an application-owned schema
- **THEN** the system does not claim that the schema matches an application-defined model

### Requirement: Application SQL composes with managed work explicitly
The system SHALL allow parameterized application SQL and managed operations to execute through one caller-owned transaction scope with one commit or rollback outcome, and any failed operation in that scope MUST prevent the transaction from committing.

#### Scenario: Mixed work commits
- **WHEN** a caller successfully writes managed data and application-owned tables through one write transaction
- **THEN** both sets of changes become durable in the same commit

#### Scenario: Application constraint rejects mixed work
- **WHEN** an application-owned foreign key, uniqueness rule, check, or trigger rejects an operation after managed work has occurred in the same transaction
- **THEN** the transaction rolls back both managed and application-owned changes and cannot continue after the failure

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

### Requirement: Application relationships avoid private managed layout
The system SHALL support database-enforced foreign keys and junction tables among application-owned SQL objects, SHALL leave those relationships under application control, and MUST NOT present private managed physical table names or mappings as stable application reference targets.

#### Scenario: Application-owned foreign key is enforced
- **WHEN** application SQL inserts a row that references a missing row in another application-owned table
- **THEN** the database rejects the write under the active transaction's failure rules

#### Scenario: Physical managed mapping is inspected
- **WHEN** inspection reports a physical table used for managed storage
- **THEN** the mapping is identified as diagnostic information rather than a portable foreign-key or schema compatibility contract

### Requirement: Inspection distinguishes managed and application-owned scope
The system SHALL identify application-owned tables as external structures during inspection and SHALL document that managed schema checks do not audit application-owned DDL or native logic beyond backend-provided integrity and foreign-key findings.

#### Scenario: Mixed database is inspected
- **WHEN** a database contains managed objects and application-owned tables
- **THEN** inspection reports both scopes without registering the application-owned tables as managed objects

#### Scenario: Application-owned trigger is present
- **WHEN** a structural check examines a database with an application-owned trigger that does not violate native integrity
- **THEN** the system neither removes the trigger nor claims to validate its application semantics

### Requirement: Backend portability boundaries remain explicit
The system SHALL treat application SQL and DDL as driver-dialect operations, SHALL support the application-owned SQL contract on SQLite, and MUST describe PostgreSQL behavior as experimental until its published capability matrix qualifies the relevant behavior.

#### Scenario: Application targets SQLite
- **WHEN** a caller uses SQLite-compatible DDL, parameters, constraints, and transaction composition
- **THEN** the application-owned schema receives the supported SQLite behavior defined by this contract

#### Scenario: Application targets PostgreSQL
- **WHEN** a caller uses the experimental PostgreSQL adapter for application-owned SQL
- **THEN** the caller supplies PostgreSQL-compatible SQL and evaluates the documented proof subset without treating it as SQLite-equivalent support
