# queries-and-mutations Specification

## Purpose
Defines explicit CRUD and bounded query behavior for managed documents and scalar tables, including optimistic document concurrency.

## Requirements

### Requirement: Explicit document mutation
The system SHALL provide insert, full-body replace, and delete operations, and conditional replace/delete SHALL require a matching positive concurrency version.

#### Scenario: Stale document replacement
- **WHEN** a caller replaces a document with an outdated expected version
- **THEN** the system raises a conflict and leaves the document unchanged

#### Scenario: Successful replacement
- **WHEN** a caller replaces a document using its current version
- **THEN** the complete body is replaced and the returned version increments

### Requirement: Typed predicates distinguish missing and null
The system SHALL support scalar comparison, membership, Boolean composition, explicit missing, and explicit null predicates while preserving scalar type distinctions.

#### Scenario: Missing and null are queried
- **WHEN** one document lacks a field and another stores JSON null
- **THEN** missing and null predicates select their respective records independently

#### Scenario: Ordinary comparison encounters null
- **WHEN** an equality or inequality predicate evaluates a missing or null field
- **THEN** that comparison does not match the record

### Requirement: Bounded deterministic queries
The system SHALL bound query limits, validate offsets, and provide deterministic ordering with immutable IDs as tie breakers.

#### Scenario: Default query
- **WHEN** a caller omits ordering and pagination arguments
- **THEN** the system returns at most the documented default limit in ascending ID order

#### Scenario: Ordered values tie
- **WHEN** multiple records have the same requested sort value
- **THEN** their relative order is ascending by ID

### Requirement: Query results are plain projections
The system SHALL return detached dictionaries or lists and SHALL allow declared table-column projections without object hydration or lazy loading.

#### Scenario: Selected columns are requested
- **WHEN** a caller queries a table with a nonempty declared projection
- **THEN** each result contains only the requested scalar columns
