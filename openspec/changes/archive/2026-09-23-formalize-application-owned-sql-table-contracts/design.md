# Design

## Context

See [proposal.md](proposal.md) for motivation. MeldDB already exposes driver-dialect parameterized SQL on database- and transaction-owned handles, identifies unmanaged tables as external during inspection, includes the complete SQLite file in physical backup, and excludes external structures from managed logical transfer. The behavior is distributed across implementation, tests, and documentation rather than presented as one supported integration contract.

MeldDB distinguishes managed objects through its private metadata registry. SQL objects not registered there remain application-owned. Existing managed migrations describe only registered managed objects; structural checking verifies managed declarations plus backend integrity and foreign-key results, but it does not have an application schema model to validate against.

## Goals / Non-Goals

**Goals:**

- Turn the existing mixed-schema behavior into one discoverable, test-backed public contract.
- Verify atomic composition of managed operations and application SQL through the existing explicit transaction scope.
- Make schema ownership, private-layout, inspection, backup, and logical-transfer boundaries difficult to misinterpret.
- Keep supported SQLite behavior and experimental PostgreSQL evidence distinct.

**Non-Goals:**

- Add an application-table registry, migration runner, schema-diff engine, ORM, tracked model, or automatic persistence behavior.
- Stabilize private physical names used by managed objects or permit application foreign keys to depend on them as a supported contract.
- Add transaction-scoped bulk SQL execution or promote PostgreSQL to supported status.
- Coordinate application payload backup or recovery outside the SQL database.

## Decisions

### 1. Define ownership by managed registration, not by a second registry

An object declared in MeldDB's managed metadata is managed; ordinary SQL objects outside that registry are application-owned. Documentation will explain this classification without exposing registry details as public API. Managed setup and migrations must leave application-owned objects alone.

This uses the boundary the database already enforces and avoids introducing duplicate metadata that could drift. A generic external-object registry was considered and rejected because it would imply that MeldDB validates or migrates schemas it does not own.

### 2. Use existing explicit SQL and transaction interfaces as the composition seam

Application DDL and DML continue to use parameterized, backend-dialect SQL. Mixed managed/application writes use one caller-owned write transaction and its transaction-owned handles. Tests will cover successful atomic commit and rollback after an application constraint or trigger failure, including the existing rule that a failed transaction cannot continue.

A new unit-of-work abstraction was rejected because it would duplicate the current transaction contract and risk hiding persistence behavior. Bulk execution remains a separate proposal because it changes ergonomics and performance, not ownership.

### 3. Keep application relationships entirely in application SQL

Applications may use native foreign keys, uniqueness constraints, checks, triggers, and junction tables among their own objects. MeldDB enables and preserves backend enforcement but does not synthesize, inspect semantically, or maintain those relationships. Inspection's managed physical mappings remain diagnostic and are not stable foreign-key targets.

Extending MeldDB's managed relationship model to external tables was rejected because it would partially adopt the application schema and create a portability dependency on private managed layout.

### 4. Treat application migrations as an application protocol

MeldDB will document that the application chooses migration identifiers, ordering, compatibility rules, and migration-history storage for application-owned objects. An application may execute its DDL through the existing SQL transaction seam, but MeldDB's managed migration ledger does not record or validate that work.

A generic application migration framework is intentionally deferred until multiple consumers demonstrate requirements that cannot be met by explicit SQL and application-owned migration bookkeeping.

### 5. Test one representative mixed-schema fixture across boundaries

Add a focused fixture containing managed data plus application-owned parent, child/junction, index, and trigger objects. Reuse it to verify:

- opening and managed migration do not adopt or rewrite application objects;
- inspection separates managed and application-owned scopes;
- successful mixed writes commit together and application constraint failures roll all work back;
- SQLite physical backup restores application tables, native objects, data, and foreign-key behavior; and
- managed logical export reports exclusions and import does not recreate application-owned objects.

Shared transaction/SQL assertions may run against the PostgreSQL test adapter when configured, but their presence remains portability evidence rather than a support promotion. SQLite-only backup assertions stay isolated to SQLite.

### 6. Make documentation the primary user-facing deliverable

Add a dedicated application-owned SQL guide and link it from the README. Align transaction, migration, inspection/recovery, logical-format, and backend-matrix wording around the same terms. The guide will include a short mixed transaction example and a responsibility table covering schema, migrations, constraints, backup, logical transfer, and application-level recovery.

Implementation code changes are expected only if the new conformance tests reveal behavior that does not meet the specs. No public API or storage-format change is planned.

## Risks / Trade-offs

- **[Risk] “Supported” is mistaken for dialect-independent application DDL.** → State that raw SQL remains driver-dialect SQL and qualify SQLite and PostgreSQL separately.
- **[Risk] Applications assume `check()` validates their domain schema.** → Document its native integrity/foreign-key coverage and explicit lack of application-model validation; test that application objects remain untouched.
- **[Risk] A physical database backup is mistaken for a complete application backup.** → Describe it as complete SQL database coverage while requiring applications such as blob stores to coordinate external payload recovery separately.
- **[Risk] Logical export is mistaken for physical backup.** → Report exclusions, verify imported destinations omit application-owned objects, and use distinct terminology in all recovery documentation.
- **[Risk] Tests overfit to private managed table names.** → Exercise managed behavior only through public handles and use inspection solely to assert scope classification.

## Migration Plan

This is a backward-compatible contract hardening change with no database-format migration. Land the conformance tests and documentation together; make the smallest implementation correction necessary only if a test exposes a contract violation. Existing applications continue using their current SQL schemas and migration processes.

Rollback consists of reverting the documentation, tests, and any narrowly scoped behavioral correction. No persisted data conversion or downgrade step is required.
