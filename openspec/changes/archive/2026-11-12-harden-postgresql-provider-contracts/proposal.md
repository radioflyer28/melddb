# Proposal

## Why

MeldStore's PostgreSQL 17 provider fixture found early commits through `COMMIT;`,
read-scope upgrades through `SET TRANSACTION`, and disconnect causes reported as
validation failures. These violate the provider boundary needed by its catalog.

## What Changes

- Reject transaction and session controls consistently through raw and bulk SQL,
  including punctuation, leading empty statements, and dialect-specific comments.
- Preserve ordinary SQL literals, identifiers, application DDL, and native bindings.
- Classify PostgreSQL disconnects as connection failures while preserving structured
  unknown outcomes, original driver causes, and quarantine without retry.
- Qualify SQLite regressions and the existing MeldStore PostgreSQL 17 fixture.

## Capabilities

### Modified Capabilities

- `explicit-transactions`: Strengthen control-command rejection and disconnect evidence.

## Impact

No runtime dependencies, storage migrations, blob APIs, or support-status changes.
Coordinates with shared `define-postgresql-provider-safety-contract` and MeldStore
`add-postgresql-metadata-support` task 1.2. PostgreSQL remains experimental.
