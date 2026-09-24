# Design

## Context

See [proposal.md](proposal.md) for motivation. MeldDB currently exposes
`Transaction.sql(statement, params)` and translates one backend execution at a
time. `Backend.execute` already separates portable transaction ownership from
SQLite and PostgreSQL driver mechanics, and transaction `_operation()` already
poisons a scope after any failed operation.

The existing application-owned SQL contract establishes the ownership boundary;
this change adds a faster explicit execution primitive without adopting external
tables. Recorded scale evidence compares checked per-record calls with direct
driver `executemany`, but does not justify bypassing MeldDB transaction or error
semantics.

## Goals / Non-Goals

**Goals:**

- Provide one small bulk SQL API that preserves existing transaction ownership,
  error translation, read-only enforcement, and backend qualification boundaries.
- Accept single-pass iterables without requiring applications to materialize large
  batches in memory.
- Return plain, portable completion evidence and define empty/failure behavior.
- Make the adapter boundary responsible for driver-specific bulk mechanics.

**Non-Goals:**

- Managed document, table, or relationship bulk APIs.
- Automatic chunking, retries, concurrency, background execution, generated SQL,
  schema adoption, or application migration bookkeeping.
- Result-set aggregation, per-row status, failing-row indexes, or a portable
  `RETURNING` abstraction.
- A standalone `Database.sql_many` convenience that silently owns a transaction.
- Promotion of PostgreSQL from experimental status or a MeldStore API change.

## Decisions

### 1. Add only `Transaction.sql_many(statement, parameter_sets)`

Bulk execution is useful precisely when many writes share an intentionally short
transaction. Requiring an explicit transaction keeps commit/rollback visible and
avoids a convenience method whose batching or transaction lifetime could be
mistaken for implicit persistence policy.

A database-level convenience and managed-object bulk methods were considered and
rejected for this change. They can be proposed later from measured workflows.

### 2. Return a plain completion summary

Successful calls return a dictionary with `parameter_sets` and `affected_rows`.
The former is the number consumed successfully. The latter is a non-negative
integer when the driver provides meaningful aggregate rowcount and `None`
otherwise. An empty iterable returns both values as zero without executing SQL.

Returning a cursor would leak backend lifetime and result semantics. Returning
only rowcount would lose input-count evidence and force a misleading value when a
driver reports rowcount as unknown. Per-parameter results would add substantial
memory and portability costs.

### 3. Stream one ordered iterable through one backend bulk call

The shared layer validates transaction ownership and the raw-SQL ownership
boundary once, peeks only far enough to identify an empty input, and wraps the
remaining iterable to count successful consumption. The adapter performs one
driver bulk call using native parameter binding. It does not split the iterable,
reorder entries, or retry.

Eager materialization was rejected because the target workloads can contain
hundreds of thousands of rows. Automatic chunking was rejected because it changes
failure timing and does not provide commits between chunks inside one transaction.

### 4. Treat the complete bulk call as one fallible transaction operation

`sql_many` runs inside the existing transaction operation guard with write intent.
That rejects read transactions before consuming input. Any statement validation,
iterator, binding, driver, constraint, or result-boundary failure marks the
transaction failed. The existing outer scope then rolls back all work, including
rows executed before the failure and any managed operations.

Backend exception translation remains the same as ordinary SQL. MeldDB will not
promise a failing parameter index because drivers do not expose it consistently.

### 5. Restrict bulk SQL to non-result-producing statements

The adapters normalize driver behavior so a statement that produces rows cannot
return successfully through `sql_many`; any writes attempted by such a statement
remain inside the poisoned transaction and are rolled back. No result rows are
exposed. Transaction and connection-control statements continue to use the same
explicit ownership guard as ordinary raw SQL.

Silently discarding `RETURNING` rows was rejected because it would conceal database
output. Aggregating result sets was rejected as a separate API with different
memory, ordering, and portability requirements.

### 6. Keep SQLite support and PostgreSQL proof status distinct

SQLite receives supported conformance coverage. The configured PostgreSQL 17/18
matrix runs the same public bulk scenarios as portability evidence, while adapter
code uses native driver parameter syntax and mechanics. Passing these cases alone
does not complete PostgreSQL migrations, structural checks, or cutover support.

The shared metadata-provider contract needs no delta: database SQL mechanics remain
MeldDB-owned, and any MeldStore adoption remains a separately pinned and qualified
change in that repository.

## Risks / Trade-offs

- **[Risk] A generator fails after the driver has executed earlier rows.** → Poison
  the transaction and require complete rollback; never return partial success.
- **[Risk] Driver rowcount semantics differ.** → Normalize unknown or negative
  rowcounts to `None` and preserve the separately counted parameter-set total.
- **[Risk] Result-producing SQL behaves differently across drivers.** → Add adapter
  conformance tests for `SELECT` and DML with a returning clause, requiring failed
  transaction semantics rather than relying on SQL keyword classification.
- **[Risk] One enormous batch still consumes driver or server resources.** → Keep
  chunk size application-controlled and document that multiple calls can share one
  transaction; do not silently buffer or split.
- **[Risk] Benchmarks encourage unsupported universal speed claims.** → Record
  environment, workload, statement counts, correctness, and direct-driver baseline;
  characterize measurements as local evidence only.

## Migration Plan

This is a backward-compatible API addition with no persisted-format migration.
Implement the adapter and public transaction method together, then add conformance,
documentation, and benchmark evidence before release. Existing `sql()` callers
continue unchanged.

Rollback consists of reverting the new method, adapter seam, tests, and docs.
Databases written through the method contain ordinary committed SQL rows and need
no data downgrade.
