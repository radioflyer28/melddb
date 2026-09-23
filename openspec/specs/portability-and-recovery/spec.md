# portability-and-recovery Specification

## Purpose
Defines inspection, integrity checking, backup, and logical transfer boundaries so recovery actions remain explicit and verifiable.

## Requirements

### Requirement: Inspection and structural checks
The system SHALL report managed and external database structures and SHALL expose a backend-appropriate structural check with explicit limitations.

#### Scenario: SQLite database is checked
- **WHEN** a caller runs the structural check on SQLite
- **THEN** the result includes integrity, foreign-key, managed-schema, and migration consistency findings

#### Scenario: PostgreSQL database is checked
- **WHEN** a caller checks the experimental PostgreSQL backend
- **THEN** the result is limited to its documented proof subset and is not represented as SQLite-equivalent integrity checking

### Requirement: Fresh-destination SQLite backup
The system SHALL create physical SQLite backups through the database backup mechanism, SHALL include the complete committed database state including managed data, application-owned SQL tables, and native objects, and SHALL refuse to overwrite an existing destination.

#### Scenario: Active WAL database is backed up
- **WHEN** a caller backs up a live SQLite database to a fresh destination
- **THEN** the destination contains one consistent snapshot including committed WAL content, managed data, application-owned tables, and their native database objects

#### Scenario: Application relationships are restored
- **WHEN** a physical backup contains application-owned tables related by database-enforced foreign keys
- **THEN** the restored database preserves those tables, rows, constraints, and relationships as part of the same database snapshot

#### Scenario: Destination exists
- **WHEN** the requested backup destination already exists
- **THEN** the operation fails without replacing it

### Requirement: Versioned logical transfer
The system SHALL export only managed data in a checksummed, versioned logical format, SHALL report application-owned tables and excluded native objects as outside that artifact, and SHALL import managed data only into a compatible new or empty destination after validation without recreating application-owned schema or records.

#### Scenario: Logical artifact is corrupted
- **WHEN** an artifact checksum or declared structure does not match its contents
- **THEN** import fails before publishing partial managed data

#### Scenario: External SQL is present
- **WHEN** a database contains application-owned SQL tables or excluded native objects
- **THEN** logical export reports them as exclusions and does not represent the artifact as a complete database backup

#### Scenario: Managed logical artifact is imported
- **WHEN** a valid logical artifact from a mixed database is imported into a compatible new or empty destination
- **THEN** the managed data is restored and the application-owned schema and records remain absent for the application to provision or recover separately

### Requirement: Backend support is not overstated
The system MUST identify physical backup as SQLite-only and PostgreSQL as experimental until full migration, structural checking, and cutover acceptance are complete.

#### Scenario: PostgreSQL physical backup is requested
- **WHEN** a caller requests the SQLite physical-backup operation from PostgreSQL
- **THEN** the system returns an unsupported-operation error
