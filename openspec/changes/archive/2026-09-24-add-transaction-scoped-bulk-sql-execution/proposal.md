# Proposal

## Why

Applications can currently compose managed operations and application-owned SQL in
one explicit transaction, but repeated application SQL requires one Python and
driver call per parameter set. Recorded MeldDB and MeldStore workloads show this
per-record path dominating large inserts, while direct driver `executemany`
baselines demonstrate a material opportunity without changing schema ownership.

## What Changes

- Add transaction-owned bulk parameterized SQL for executing one driver-dialect
  statement against multiple parameter sets inside an existing explicit transaction.
- Preserve transaction ownership and failure semantics: the caller controls the
  surrounding commit, and any validation, constraint, driver, or iteration failure
  poisons the transaction and causes the whole scope to roll back.
- Define deterministic input and result behavior, including empty batches,
  affected-row reporting, and rejection of result-producing or transaction-control
  statements.
- Provide equivalent public behavior on supported SQLite and the experimental
  PostgreSQL proof while keeping backend-specific bulk mechanics in adapters.
- Document and benchmark the capability against both ordinary row-by-row SQL and a
  direct-driver baseline without making universal performance claims.
- Keep managed collection/table/relationship bulk mutation, automatic batching,
  retries, background work, and application-specific schemas outside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `application-owned-sql`: Allow application-owned rows to be written in bulk
  through the same caller-owned transaction that composes with managed work.
- `explicit-transactions`: Define the transaction-owned bulk SQL interface,
  ownership checks, result boundary, and fail-closed behavior.

## Impact

- Public API: add a bulk SQL method to the transaction-owned handle; no standalone
  database convenience method is included in the initial contract.
- Implementation: extend the shared database seam and SQLite/PostgreSQL backend
  adapters with translated bulk execution while preserving existing errors.
- Tests and documentation: add SQLite conformance, configured PostgreSQL proof
  coverage, transaction-failure cases, examples, and measured benchmarks.
- Dependencies and persisted formats: no new runtime dependency, managed schema,
  database-format migration, or logical-transfer format change.
- Consumers: MeldStore may evaluate and adopt the new API in its own repository and
  release cycle; this proposal does not change the shared metadata-provider contract.
