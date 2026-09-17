# Proposal

## Why

SQLite consumers such as MeldStore must currently open separate `sqlite3`
connections to select persistent journal mode, inspect effective settings, maintain
planner statistics, and checkpoint WAL. MeldDB should own these database-level
operations through a small explicit API so consumers can avoid private backend access
without giving up observable control or safety.

## What Changes

- Add an explicit SQLite open policy that can preserve, select, and validate journal
  mode for both new and existing file-backed databases.
- Expose structured SQLite runtime information, including effective connection/file
  settings, loaded SQLite version, and capability/safety decisions.
- Add explicit statistics and WAL-checkpoint maintenance with structured results,
  including honest reporting of busy or partial checkpoints.
- Define and document a conservative SQLite runtime-safety policy, including the
  versions in which WAL operation is permitted and how callers may select rollback
  journaling when WAL is unsafe.
- Keep these operations unavailable on PostgreSQL and inapplicable operations explicit
  for read-only or in-memory databases.
- Preserve MeldDB's raw-SQL restrictions and do not expose the underlying driver
  connection.

## Capabilities

### New Capabilities

- `sqlite-runtime-management`: Explicit journal policy, effective runtime reporting,
  SQLite safety qualification, planner-statistics maintenance, and WAL checkpoints.

### Modified Capabilities

None.

## Impact

The public SQLite opening surface and `Database` API gain additive configuration,
inspection, and maintenance entry points. SQLite adapter setup, error translation,
tests, user documentation, backend qualification, and the MeldStore adapter seam are
affected. The dependency-free core and current PostgreSQL behavior remain unchanged;
the shared MeldDB/MeldStore compatibility contract should be reviewed before MeldStore
updates its pinned MeldDB revision.
