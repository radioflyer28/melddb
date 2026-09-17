# data-models Specification

## Purpose
Defines MeldDB's plain-data document, scalar-table, and directed-relationship models without tracked objects or hidden persistence.

## Requirements

### Requirement: Detached document values
The system SHALL store documents as an ID, concurrency version, and portable JSON body, and SHALL return detached plain values whose local mutation does not persist automatically.

#### Scenario: Document is read and mutated locally
- **WHEN** a caller changes a nested value in a returned document without issuing a write
- **THEN** reopening or rereading the record returns the previously persisted body

### Requirement: Declared scalar tables
The system SHALL support migration-declared tables with immutable text IDs and typed text, signed-64-bit integer, finite-float, boolean, and bytes columns.

#### Scenario: Partial table update
- **WHEN** a caller updates a declared subset of columns for an existing row
- **THEN** only those columns change and the immutable ID remains unchanged

#### Scenario: Invalid typed value
- **WHEN** a supplied value falls outside the declared column contract
- **THEN** the system rejects it without mutating the row

### Requirement: Directed declared relationships
The system SHALL support migration-declared directed relationships with typed endpoints, unique endpoint pairs, detached JSON properties, and explicit restrict-or-cascade link deletion behavior.

#### Scenario: Restricted endpoint deletion
- **WHEN** an endpoint with an incident restrict relationship is deleted
- **THEN** the database constraint rejects deletion and preserves the endpoint and link

#### Scenario: Cascading link deletion
- **WHEN** an endpoint of a cascade relationship is deleted
- **THEN** incident links are removed but neighboring records are preserved

### Requirement: Bounded relationship traversal
The system SHALL provide deterministic directed traversal with explicit depth, node, and edge budgets and SHALL return no partial result when a budget is exceeded.

#### Scenario: Cycle is traversed
- **WHEN** traversal encounters cycles or self-links within the declared relationship
- **THEN** visited tracking prevents repeated expansion and results remain unique

#### Scenario: Budget is exceeded
- **WHEN** traversal would exceed a caller-supplied node or edge budget
- **THEN** the system raises a traversal limit error without returning partial records
