# Inspection and recovery

`db.inspect()` returns logical-to-physical mappings, managed declarations,
recorded migrations and external table names. `db.check()` checks the database
in one read transaction, returning `{"ok": bool, "errors": [...]}`. Neither
operation repairs the inspected database or rewrites application records.

SQLite checking includes:

- Native integrity and foreign-key checks.
- Migration operation validation and checksum verification.
- Recreating declared structures in a separate, empty in-memory database and
  comparing managed tables, indexes and triggers with `sqlite_schema`.
- Logical-to-physical mapping validation and unexpected triggers on managed tables.
- Validating existing data against declared required, primitive-type and
  uniqueness rules, including rules enforced by triggers.

Failures identify structures using `missing_structure`, `changed_structure`,
`physical_mapping` or `unexpected_trigger`. Metadata/checksum errors use
`invalid_metadata` and `migration_checksum`; data violations use `constraint_data`
with bounded violation details. Native integrity/FK failures also appear in
`errors`. Unsupported/incomplete format metadata may prevent opening the database
and raises `MigrationError` instead of returning a check report.

This is conservative verification of library-generated structures. Equivalent
handwritten DDL can be reported as changed; the checker does not prove arbitrary
SQL equivalence. Column declaration order is preserved when comparing tables,
since canonical metadata does not retain it. Extra application indexes are
permitted; extra triggers on managed tables are reported because they can alter
write behavior. External tables and their native logic are not audited against
an application schema. The checker is not authentication against an attacker
who can rewrite both the database and its metadata.

PostgreSQL remains experimental: checks validate migration checksums and managed
table existence, not full native structure or database integrity. Do not treat
its report as equivalent to SQLite's report. S09 does not expand that boundary.

## Read-oriented CLI

```console
uv run melddb inspect application.db
uv run melddb check application.db
uv run melddb backup application.db restored.db
uv run melddb export application.db managed.json
```

All commands open the source read-only. A misspelled path fails without creating
a database. `inspect` and `check` reject destination arguments. Output is JSON;
`check` exits 1 on a failed report. Expected library/filesystem failures print
a concise error to stderr; invalid arguments exit 2. SQLite may create normal
WAL coordination sidecars while opening a live WAL database read-only; no
application data or schema is changed.

## Physical backup and restoration

`db.backup(new_path)` uses SQLite's online backup API while the source may be
open in WAL mode. It includes external tables and native database objects.
It cannot run inside a library-owned application transaction. PostgreSQL physical
backup remains unsupported.

The library writes a uniquely named temporary artifact beside the destination,
checks integrity/references, switches the detached copy to DELETE journal mode,
then reopens and checks its managed structures and constraints. Only a passing,
standalone artifact is fsynced and published using a no-overwrite hard link.
The source journal mode stays unchanged. The destination filesystem must support
hard links; filesystem errors are surfaced rather than using an unsafe overwrite.

To restore, choose a fresh path, create the backup there, open that destination,
and call `check()` before using it. The file is already the restored database;
there is no destructive restore-in-place command. See `examples/recovery.py`.
Keep the original until the restored application data has been checked. Subsequent
writes to the restored database are independent of the source.

A pre-existing destination, including one created during backup publication,
is never overwritten. Ordinary failure removes this attempt's temporary file.
Process interruption may leave `.partial-<random>` files; a completed destination
is either absent or fully published. After confirming that no backup attempt is
active, an operator may remove abandoned temporary files. The library does not
delete other attempts' artifacts automatically.

Tests cover process interruption during copying and immediately before/after
publication, live WAL backup, binary values/document versions/relationships,
external data, independent restored writes, invalid structure rejection and
destination races. These are process-crash tests, not a guarantee against every
power-loss or filesystem failure. Logical export/import portability is S10.
