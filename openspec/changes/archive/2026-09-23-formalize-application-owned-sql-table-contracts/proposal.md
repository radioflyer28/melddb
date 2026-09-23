# Proposal

## Why

MeldDB applications such as MeldStore already keep authoritative relational data in ordinary application-owned SQL tables beside MeldDB-managed objects, but that integration pattern is only implied across raw-SQL, transaction, and recovery documentation. Formalizing it now gives consumers a stable ownership and recovery contract before any generic external-table migration tooling is considered.

## What Changes

- Define application-owned SQL tables and native database objects as a first-class integration pattern that MeldDB preserves but does not adopt, rewrite, validate against an application schema, or migrate.
- State that applications own their table DDL, indexes, triggers, constraints, migration history, and compatibility policy.
- Define supported composition through MeldDB's parameterized SQL and caller-owned transaction scopes, including rollback when application constraints reject mixed managed/application work.
- Define relationship boundaries: foreign keys and junction tables among application-owned tables are supported by the database, while references to MeldDB's private physical managed layout are outside the compatibility contract.
- Clarify that a physical SQLite backup covers the complete database, including application-owned tables and native objects, while MeldDB logical export/import covers only managed data and is not a whole-application backup or migration mechanism.
- Add focused documentation and conformance tests for mixed schemas, ownership boundaries, shared transactions, foreign-key failures, inspection, backup, and logical-export exclusions.
- Keep PostgreSQL behavior experimental and separately qualified; this change does not promote it to supported status.
- Defer transaction-scoped bulk SQL execution, automatic schema diffing, and a generic application-table migration framework.

## Capabilities

### New Capabilities

- `application-owned-sql`: Defines coexistence, ownership, transaction composition, relationship boundaries, inspection, and backend portability for application-owned SQL tables and native objects.

### Modified Capabilities

- `portability-and-recovery`: Makes the whole-database scope of physical SQLite backup and the managed-only scope of logical export/import explicit, including application-owned native objects and restore responsibilities.

## Impact

- Public behavior and documentation around `Database.sql()`, `Transaction.sql()`, `inspect()`, `check()`, SQLite backup, and logical export/import become an explicit consumer contract.
- Tests will exercise ordinary application DDL and data alongside managed MeldDB objects, including application-owned foreign keys and failure rollback.
- Existing database formats and public APIs remain compatible; no third-party core dependency, ORM behavior, automatic persistence, or application-schema migration API is introduced.
- SQLite is the supported target. PostgreSQL coverage remains an experimental portability proof and must be described and tested separately where applicable.
