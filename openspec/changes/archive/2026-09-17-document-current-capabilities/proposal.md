# Proposal

## Why

MeldDB has a qualified release candidate and extensive behavioral documentation,
but no canonical OpenSpec capability inventory. A compact baseline makes future
changes reviewable against what the library demonstrably does today.

## What Changes

- Record current public behavior as OpenSpec requirements without changing code.
- Preserve the distinction between supported SQLite behavior and experimental PostgreSQL behavior.
- Keep historical measurements and implementation detail in the existing documentation.

## Capabilities

### New Capabilities

- `explicit-transactions`: Connection ownership, explicit transaction scopes, raw SQL composition, and failure behavior.
- `data-models`: Plain-data collections, scalar tables, and directed relationships.
- `queries-and-mutations`: Explicit CRUD, predicates, ordering, pagination, and optimistic document updates.
- `schema-evolution`: Declared creation and migration behavior with validation and rollback.
- `portability-and-recovery`: Logical transfer, inspection, structural checks, physical SQLite backup, and backend boundaries.

### Modified Capabilities

None.

## Impact

Only OpenSpec planning artifacts are added. Public APIs, storage formats,
dependencies, runtime behavior, and existing documentation remain unchanged.
