# Proposal

## Why

MeldStore's PostgreSQL migration dry runs must check deferred constraints before
rolling back. Raw SQL correctly rejects transaction controls, so a public provider
operation is needed instead of private connection access or a control-command bypass.

## What Changes

- Add transaction-owned constraint validation with normal failure poisoning.
- Document PostgreSQL's immediate-mode effect and SQLite's foreign-key scan.
- Qualify application constraints, ownership, and rollback without committing.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `explicit-transactions`: explicit validation before caller-controlled completion.

## Impact

MeldDB owns the method, backend mechanics, tests and documentation. MeldStore
qualifies the published exact revision; the shared store records the dependency.
The core remains dependency-free. PostgreSQL remains experimental.
