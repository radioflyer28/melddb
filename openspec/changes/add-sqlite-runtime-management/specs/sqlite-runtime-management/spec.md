# Spec Delta

## Purpose

Defines explicit SQLite configuration, runtime qualification, and maintenance so applications can manage supported database behavior without accessing MeldDB's private driver connection.

## ADDED Requirements

### Requirement: Journal policy is explicit and verified
The system SHALL let callers preserve or select `wal` or `delete` journal mode when opening a file-backed SQLite database, SHALL apply an explicit selection to both new and existing databases, and SHALL verify the effective mode before returning the database handle.

#### Scenario: Existing database adopts selected WAL mode
- **WHEN** a caller opens an existing rollback-journal database with `wal` explicitly selected and the runtime safety policy permits WAL
- **THEN** the database is converted to persistent WAL mode and the returned handle reports `wal` as effective

#### Scenario: Existing journal mode is preserved
- **WHEN** a caller opens an existing database without selecting a journal-mode change
- **THEN** its existing journal mode is preserved and validated against the runtime safety policy

#### Scenario: New database uses the default policy
- **WHEN** a caller creates a file-backed SQLite database without selecting a journal mode
- **THEN** the documented default selects WAL only when the runtime safety policy permits it

#### Scenario: Read-only mode cannot satisfy a requested change
- **WHEN** a read-only open requests a journal mode different from the database's effective mode
- **THEN** the system rejects the open without modifying the database

#### Scenario: SQLite refuses the selected mode
- **WHEN** the requested journal-mode transition cannot acquire the required lock or the underlying VFS leaves another mode effective
- **THEN** the system reports a translated busy or unsupported failure and does not return a mismatched handle

### Requirement: Effective SQLite runtime is observable
The system SHALL return a detached plain-data report containing the backend, loaded SQLite version, file-backed and read-only state, effective journal mode, synchronous level, foreign-key enforcement, and named runtime capabilities with qualification reasons.

#### Scenario: Application verifies live configuration
- **WHEN** a caller requests the runtime report from an open SQLite database
- **THEN** the report reflects settings read from that live connection rather than merely echoing requested values

#### Scenario: In-memory runtime is reported
- **WHEN** a caller requests the report from an in-memory SQLite database
- **THEN** the report identifies memory journaling and marks file-only configuration and maintenance capabilities unavailable

#### Scenario: PostgreSQL handle requests SQLite runtime information
- **WHEN** a caller invokes the SQLite runtime interface on a PostgreSQL database
- **THEN** the system raises an unsupported-operation error instead of returning SQLite-shaped data

### Requirement: SQLite runtime safety is fail-closed
The system MUST apply a documented safety policy before enabling writable WAL operation, MUST reject a runtime that does not meet that policy before managed or application writes occur, and MUST expose the policy decision and reason in runtime reporting.

#### Scenario: Unqualified runtime requests writable WAL
- **WHEN** a new or existing writable database would operate in WAL mode on a loaded SQLite version not accepted by the documented policy
- **THEN** opening fails with actionable guidance to upgrade SQLite or explicitly select `delete`

#### Scenario: Safe rollback-journal fallback is selected
- **WHEN** the same runtime opens a file-backed database with `delete` explicitly selected
- **THEN** the system permits the open if all other required SQLite capabilities pass

#### Scenario: Capability validation fails during open
- **WHEN** a runtime capability probe or effective-setting validation fails
- **THEN** the connection is closed and the system does not leave a newly requested journal transition falsely reported as active

### Requirement: Statistics maintenance is explicit
The system SHALL provide explicit bounded statistics maintenance using SQLite's recommended optimization operation by default, SHALL allow a caller to request full analysis deliberately, and SHALL return a structured result identifying the action and outcome.

#### Scenario: Default statistics maintenance runs
- **WHEN** a caller requests statistics maintenance without selecting full analysis
- **THEN** the system runs the documented bounded optimization policy and reports `optimize` as the completed action

#### Scenario: Full analysis is requested
- **WHEN** a caller explicitly requests full analysis on a writable file-backed database
- **THEN** the system updates persistent planner statistics and reports `analyze` as the completed action

#### Scenario: Maintenance fails
- **WHEN** statistics maintenance encounters a lock, I/O, or SQLite error
- **THEN** the system raises a translated error and does not return a successful result

### Requirement: WAL checkpoints return structured progress
The system SHALL support explicit named SQLite checkpoint modes and SHALL return the requested mode, busy status, log-frame count, checkpointed-frame count, and whether the requested checkpoint completed.

#### Scenario: Passive checkpoint is partially pinned
- **WHEN** active readers prevent a passive checkpoint from copying every WAL frame
- **THEN** the result reports the remaining frames and does not represent the checkpoint as complete

#### Scenario: Truncating checkpoint is busy
- **WHEN** a reader or writer prevents a truncating checkpoint from completing
- **THEN** the result reports busy status without claiming that the WAL was truncated

#### Scenario: Database is not using WAL
- **WHEN** checkpoint maintenance runs against a rollback-journal database
- **THEN** the structured result identifies that no WAL is active rather than reporting fabricated frame counts

### Requirement: Runtime management respects connection ownership
The system SHALL restrict configuration and maintenance to the database-owning thread, SHALL reject maintenance during an active MeldDB transaction, and SHALL not expose a raw SQLite connection.

#### Scenario: Maintenance is requested inside a transaction
- **WHEN** a caller invokes SQLite maintenance while an explicit transaction is active
- **THEN** the operation is rejected and the transaction is marked unable to commit

#### Scenario: Maintenance is requested through a read-only or in-memory handle
- **WHEN** a caller requests a mutating statistics or checkpoint operation from a handle that cannot support it
- **THEN** the system raises an unsupported-operation error before attempting maintenance

#### Scenario: Maintenance crosses a thread
- **WHEN** a database handle is used from a thread other than its creator to request runtime management
- **THEN** the system rejects the operation without performing SQLite I/O
