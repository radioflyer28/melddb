# Design

## Context

See `proposal.md` for motivation. MeldDB currently configures foreign keys and
`synchronous=FULL` on every SQLite connection, selects WAL only when it creates a
new file, and intentionally blocks PRAGMA statements from the raw SQL escape hatch.
MeldStore consequently opens control connections around MeldDB to configure existing
files, run planner-statistics work, and checkpoint WAL.

Journal mode is persistent database state, while foreign-key enforcement and
synchronous level are live connection settings. SQLite's checkpoint and optimization
operations also have distinct concurrency and result semantics. The public interface
must keep those distinctions visible without returning the private connection.

## Goals / Non-Goals

**Goals:**

- Let applications select or preserve journal mode through the normal SQLite open.
- Report requested-versus-effective behavior as detached plain data.
- Centralize safety qualification and SQLite error translation.
- Make planner maintenance and checkpoint progress explicit and testable.
- Keep the API small enough for MeldStore to remove its MeldDB-side control connection.

**Non-Goals:**

- General-purpose PRAGMA execution or arbitrary connection tuning.
- Automatic background maintenance, scheduling, or cross-process exclusivity.
- Changing PostgreSQL behavior or claiming equivalent PostgreSQL operations.
- Replacing application coordination around disruptive maintenance.
- Managing cache size, page size, mmap, temp storage, or vacuum policy in this change.

## Decisions

### Extend SQLite open with a narrow journal selector

Add a `journal_mode` keyword to `melddb.open()`/`Database` with values `None`,
`"wal"`, or `"delete"`. `None` preserves the existing compatibility behavior:
new file-backed databases select WAL when safe, existing databases preserve their
mode, and in-memory databases remain memory-journaled. An explicit value is both a
requested transition and a postcondition checked on the live connection.

For read-only handles, an explicit value acts only as an assertion: the open succeeds
when it already matches and otherwise fails without attempting mutation. This is
preferred to a separate pre-open helper because the transition, capability probes,
connection settings, and cleanup then share one error boundary.

### Return plain runtime reports from `sqlite_runtime()`

Add `Database.sqlite_runtime()` returning a new detached dictionary on each call.
The stable fields cover backend, `sqlite_version`, file/read-only state,
`journal_mode`, `synchronous`, `foreign_keys`, and a `capabilities` mapping whose
entries contain an available Boolean and machine-readable reason. The initial named
capabilities are `wal`, `statistics`, and `checkpoint`.

The report queries effective values from the live connection. It is not a mutable
settings object and does not expose driver handles. A SQLite-specific method is
preferred to expanding `inspect()`, whose current contract describes persistent
MeldDB/application structures and also supports PostgreSQL.

### Make the runtime-safety policy a backend-owned pure decision

Keep safety qualification in the SQLite adapter as a pure function of loaded SQLite
version, requested/effective mode, read-only state, and existing capability probes.
The initial WAL allowlist follows SQLite's documented WAL-reset fix: 3.51.3 or newer,
plus the 3.50.7 and 3.44.6 backport lines. Writable WAL fails closed outside that
allowlist; explicit DELETE mode remains available when the existing JSON and version
requirements pass. Read-only WAL can be reported without enabling writable WAL.

The allowlist and its rationale belong in user documentation and focused tests because
it will evolve as supported runtimes change. A generic "unsafe override" is rejected:
it would make the library report an unsupported durability posture as supported.

### Add one explicit `maintain_sqlite()` operation

Add `Database.maintain_sqlite(*, statistics="optimize", checkpoint="passive")`.
Each argument may be `None`; statistics accepts `"optimize"` or `"analyze"`, and
checkpoint accepts SQLite's named `"passive"`, `"full"`, `"restart"`, or
`"truncate"` modes. At least one action must be selected. The result is a plain
dictionary with independent `statistics` and `checkpoint` sections.

`optimize` uses the current SQLite-recommended bounded policy for a fresh/long-lived
connection; `analyze` remains an intentionally expensive opt-in. Checkpoint output is
normalized to `{mode, busy, log_frames, checkpointed_frames, complete, wal_active}`.
The SQLite `-1/-1` no-WAL result becomes `wal_active: false`, not a false successful
checkpoint. Partial PASSIVE progress is distinguished from the busy flag returned by
FULL/RESTART/TRUNCATE.

One public method is preferred to separate statistics/checkpoint methods because both
are explicit SQLite maintenance, share availability validation, and MeldStore commonly
runs them together. The result sections remain independent so callers can request only
one action.

### Preserve ownership and transaction boundaries

Runtime reporting uses the existing database-owned read operation. Journal selection
happens during open before the handle is returned. Maintenance calls `_available()`
and executes outside any caller transaction; invoking it during an active transaction
poisons that transaction consistently with existing ownership rules.

Maintenance requires a writable, file-backed SQLite handle. MeldDB does not invent an
exclusive-maintenance lock: checkpoints already expose contention and no library-local
lock can exclude uncooperative processes. Applications such as MeldStore may retain
their own cooperative maintenance lease around the MeldDB call.

### Keep backend mechanics private

SQLite PRAGMA construction is limited to validated enum values in the adapter. Driver
rows and errors are normalized before reaching `Database`; PostgreSQL receives
`UnsupportedError`. Raw `Database.sql()` continues to reject PRAGMA statements.

## Risks / Trade-offs

- **Opening an existing database can now intentionally change persistent journal state**
  → Require an explicit selector, verify the returned mode, document locking effects,
  and preserve the old behavior when omitted.
- **The WAL safety allowlist will age** → Isolate the decision, document its source,
  test accepted/rejected branches, and report the decision at runtime.
- **ANALYZE or blocking checkpoint modes can be expensive** → Keep `optimize` and
  PASSIVE as defaults; require explicit opt-in for full analysis and stronger modes.
- **A successful API call cannot prove global process exclusivity** → Return actual
  SQLite checkpoint progress and leave cooperative deployment locks to applications.
- **Changing journal mode may be partially observable if later open validation fails**
  → Perform capability checks before mutation where possible, report the effective
  mode honestly, and document that SQLite journal transitions are persistent rather
  than transactional configuration.

## Migration Plan

1. Add adapter-level policy evaluation, journal selection, reporting, and maintenance
   primitives with focused SQLite tests.
2. Add the public open keyword and `Database` methods, preserving current defaults.
3. Update qualification and user documentation with accepted SQLite runtimes,
   persistent journal-mode semantics, maintenance concurrency, and structured results.
4. Update MeldStore in its own change to use these public methods for the MeldDB
   adapter while retaining its cooperative maintenance lease; keep the direct sqlite3
   adapter independent.
5. Review the shared metadata-provider contract and run MeldStore adapter conformance
   before advancing its pinned MeldDB revision.

Rollback removes the additive public methods and keyword. Databases explicitly moved
to WAL or DELETE retain that persistent SQLite state; operators can select the desired
mode with a compatible tool before returning to an older MeldDB release.

## Shared Contract Review

No separate shared-store delta is required for this implementation. The existing
`metadata-provider-contract` already assigns database connection/transaction semantics
to MeldDB and requires MeldStore adapter review before updating its pinned MeldDB
revision. MeldStore adoption remains a separate repository-local change; that change
should reference this capability and retain MeldStore's cooperative maintenance lease.
