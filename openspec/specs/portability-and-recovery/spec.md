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
The system SHALL create physical SQLite backups through the database backup mechanism, include application-owned SQL tables, and refuse to overwrite an existing destination.

#### Scenario: Active WAL database is backed up
- **WHEN** a caller backs up a live SQLite database to a fresh destination
- **THEN** the destination contains a consistent database including committed WAL content and external tables

#### Scenario: Destination exists
- **WHEN** the requested backup destination already exists
- **THEN** the operation fails without replacing it

### Requirement: Versioned logical transfer
The system SHALL export managed data in a checksummed, versioned logical format and import it only into a compatible new or empty destination after validation.

#### Scenario: Logical artifact is corrupted
- **WHEN** an artifact checksum or declared structure does not match its contents
- **THEN** import fails before publishing partial managed data

#### Scenario: External SQL is present
- **WHEN** a database contains application-owned SQL tables
- **THEN** logical export reports those tables as outside the managed logical artifact rather than silently claiming to include them

### Requirement: Backend support is not overstated
The system MUST identify physical backup as SQLite-only and PostgreSQL as experimental until full migration, structural checking, and cutover acceptance are complete.

#### Scenario: PostgreSQL physical backup is requested
- **WHEN** a caller requests the SQLite physical-backup operation from PostgreSQL
- **THEN** the system returns an unsupported-operation error
