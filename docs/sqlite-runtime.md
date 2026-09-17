# SQLite runtime configuration and maintenance

MeldDB keeps SQLite configuration explicit without exposing its private driver
connection. Journal mode is persistent database state; synchronous level and foreign
key enforcement are settings on the live connection. Runtime reports return effective
values, not merely the values requested by the caller.

## Journal policy

`melddb.open()` accepts `journal_mode="wal"` or `journal_mode="delete"` for a
file-backed SQLite database:

```python
import melddb

with melddb.open("application.db", journal_mode="delete") as db:
    assert db.sqlite_runtime()["journal_mode"] == "delete"
```

The option applies to new and existing files. A successful open verifies SQLite's
returned effective mode. Changing mode may require an exclusive lock and may fail with
`BusyError` when another connection is active. The transition is persistent SQLite
state, not a transaction that MeldDB can roll back after later configuration failure.

When `journal_mode` is omitted, MeldDB preserves its compatibility behavior:

- Existing databases retain their current mode.
- New file-backed databases select WAL when the loaded SQLite is qualified for
  writable WAL, otherwise they select DELETE.
- In-memory databases retain SQLite's memory journal and reject a file-journal
  selection.
- A read-only handle never changes journal mode. An explicit mode is an assertion and
  fails if the file does not already use that mode.

MeldDB always requests `synchronous=FULL` and foreign-key enforcement on its live
SQLite connection. An external direct SQLite connection must enable its own foreign
keys.

## WAL runtime-safety policy

SQLite documents a rare WAL-reset corruption race affecting writable WAL databases
with concurrent connections. MeldDB permits writable WAL only for SQLite 3.51.3 or
newer, or the fixed 3.50.7 and 3.44.6 backport release lines. Earlier or unpatched
versions can still use explicit DELETE mode if they satisfy MeldDB's other capability
checks. There is no unsafe override.

An explicit WAL request fails before creating a new database when the runtime is not
qualified. Opening an existing writable WAL database also fails closed. Read-only WAL
inspection remains possible when SQLite itself can open the file.

The policy follows SQLite's [WAL documentation](https://www.sqlite.org/wal.html) and
[3.51.3 release notes](https://www.sqlite.org/releaselog/3_51_3.html). It is separate
from MeldDB's JSON-path capability probe and may evolve as supported SQLite releases
change.

## Effective runtime report

`db.sqlite_runtime()` returns a detached dictionary containing the backend, loaded
SQLite version, file/read-only state, effective journal and synchronous modes,
foreign-key enforcement, and named `wal`, `statistics`, and `checkpoint` capabilities.
Each capability includes availability and a machine-readable reason. Mutating the
report has no effect on the database. PostgreSQL rejects this SQLite-specific method.

## Statistics and checkpoints

Maintenance is explicit and is never scheduled in the background:

```python
with melddb.open("application.db") as db:
    result = db.maintain_sqlite()
    checkpoint = result["checkpoint"]
    if checkpoint["wal_active"] and not checkpoint["complete"]:
        print("checkpoint remains incomplete", checkpoint)
```

`maintain_sqlite(statistics="optimize", checkpoint="passive")` accepts statistics
of `None`, `"optimize"`, or `"analyze"`, and checkpoints of `None`, `"passive"`,
`"full"`, `"restart"`, or `"truncate"`. At least one action is required.

The default optimization uses `PRAGMA optimize=0x10002`, SQLite's bounded
recommendation for examining all tables on a fresh connection. On SQLite before 3.46,
MeldDB temporarily applies an analysis limit and restores the connection's prior value.
Full `ANALYZE` is an explicit, potentially expensive opt-in.

Checkpoint results report mode, busy status, WAL/log frame counts, completed frame
counts, completion, and whether WAL is active. PASSIVE checkpoints can make partial
progress without setting SQLite's busy result; MeldDB compares frame counts instead of
treating `busy == false` as completion. Rollback-journal databases report
`wal_active: false` and do not fabricate frame counts.

Maintenance requires a writable file-backed SQLite handle, the creating thread, and
no active MeldDB transaction. FULL, RESTART, and TRUNCATE can interfere with concurrent
writers or readers. MeldDB does not claim global exclusivity: applications should
retain cooperative maintenance leases when needed and handle uncooperative processes
through the structured result and translated errors.
