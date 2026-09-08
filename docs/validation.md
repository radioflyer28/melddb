# Local validation evidence — 2026-09-08

Environment: Windows host, Python 3.12.10, SQLite 3.49.1, Psycopg 3.3.5,
Pytest 9.1.1, Hypothesis 6.167.1. PostgreSQL runs in disposable Linux containers
through Docker Desktop's WSL2 engine (Docker 28.1.1).

| Server | Shared suite result |
| --- | --- |
| PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2) plus SQLite | 74 passed, 2 skipped |
| PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2) plus SQLite | 74 passed, 2 skipped |

Each command used `uv run --offline --extra test --extra postgres pytest
-p no:cacheprovider -q` with MELDDB_TEST_POSTGRES set to the relevant disposable
server. Cacheprovider was disabled because an old sandbox-owned pytest cache
has an unrelated Windows permission issue. This does not skip any tests.

The expected skips are PostgreSQL schema evolution (outside the proof) and
the PostgreSQL-only unsupported-operation boundary test in its SQLite case.

New evidence:

- Shared rollback tests now assert links as well as document and row counts.
- Raw SQL cannot insert null record IDs or change existing IDs on either backend.
- Connection setup/configuration errors preserve the driver exception as cause;
  acquired connections close on failed setup. These are fault-injection tests.
- Language-neutral fixture checks missing/null, booleans versus numbers,
  exact interoperable integer limits, membership, case ordering and pagination.
- Mixed SQLite logical export imports into both backends, preserving document
  versions/IDs, int64 values and links.
- Unsupported PostgreSQL evolution rejects a mixed revision without leaving
  created objects or a migration record.
- Test-owned PostgreSQL schemas are cleaned up through finally blocks.
- Ruff passed. CI now has PostgreSQL 17/18 service jobs and runs the executable
  example in the existing OS/Python matrix.
- Wheel and source distribution built. A fresh Python 3.12 environment installed
  the wheel with no dependencies and passed an isolated document round trip.
  Source packaging now includes crash workers, JSON fixtures and examples.

Scope limits: these are local runs, not evidence that GitHub CI ran. The
Windows/Python host matrix is incomplete. Performance
fixtures, schema-drift verification, adversarial artifact validation and release
qualification remain open in implementation-plan.md. Both database adapters
remain alpha; PostgreSQL remains experimental.

Subsequent S04 checkpoint: the expanded comparative workload passes 27 tests
across MeldDB, sqlite3 helpers and SQLAlchemy Core. The full SQLite-only run
after S04 passed 71 tests with one expected PostgreSQL-only skip; Ruff passed.
See gate-a.md for the scoped Gate A decision and gate-a-results.json for measurements.

## S05/S06 checkpoint

Full suite on the same Windows/Python 3.12 host, using the isolated PostgreSQL
17.11 and 18.6 services: **217 passed, 2 expected skips per run**. Each run also
includes SQLite. Ruff passed and examples/query_crud.py completed successfully.
The skips remain the documented backend-specific evolution/boundary tests.

The new shared suite covers all scalar comparison operators, Boolean
combinations, empty/bounded membership, object-only paths through mixed
objects/arrays, escaped keys, deterministic ascending/descending pagination,
invalid options before storage exists, replace/delete/conflict semantics,
version exhaustion, every relational type, atomic invalid writes, projections,
null handling, reference-model predicates and existing parameterized SQL with
WITH/RETURNING. Finite-float boundaries include subnormal and maximum values.

Corrections include PostgreSQL object-path guards and explicit ID collation,
connection-local JSONB numeric decoding, finite float-column normalization,
strict query option/version bounds, and consistent missing-document behavior.
No physical schema change was required; storage remains format 2.

PostgreSQL JSON adaptation uses the documented per-connection context:
[Psycopg JSON adaptation](https://www.psycopg.org/psycopg3/docs/basic/adapt.html#json-adaptation).
The optional dependency remains outside the core installation. These local
results do not substitute for the outstanding complete OS/Python CI matrix.

Container images used:

- postgres:17 — sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675
- postgres:18 — sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280

Images were used as test services with localhost-only ports and disposable
storage. No application database was modified by these runs.

## S07 checkpoint

Full SQLite plus PostgreSQL suites passed against both 17.11 and 18.6:
**281 passed, 2 expected skips per run** on the Windows/Python 3.12 host above.
Ruff and the executable dependency example passed. Local service URLs used
`127.0.0.1` and `connect_timeout=10` after an initial `localhost` connection
stalled; that interrupted run is not counted as successful evidence.

The 64 added shared cases cover every collection/table endpoint combination
with both deletion policies and endpoint deletion directions, equal IDs across
stores, detached properties, duplicate/invalid writes, transaction poisoning,
minimum depths, cycles/self-links, exact and exceeded budgets, pagination,
batched wide frontiers, and a concurrent deletion between discovery and record
retrieval. Hypothesis compares both traversal directions with an in-memory BFS.

Corrections validate reference IDs, bound pagination/traversal integers for both
drivers, explicitly collate edge listing IDs, and count the starting record in
the node budget for heterogeneous relationships as well as homogeneous ones.
No physical schema change or runtime dependency was introduced.

The 10,000-document/50,000-edge SQLite workload passes with identical records
and minimum depths versus sqlite3. Both use 51 batched SELECTs; the MeldDB
traversal issues 57 total SQL statements. Exact edge overflow and integrity
checks pass. See [relationships](relationships.md) and the machine-readable
[scale report](s07-scale-results.json) for timings, hardware and limitations.
Reproduce with `uv run python validation/traversal_scale.py`.

CI now runs the dependency example in its OS/Python matrix and the scale
workload in its Linux validation job. These edits are not evidence of executed
CI or complete release qualification. S08/Gate B remain next; UUIDv7 evaluation
is tracked separately before the API freeze.

## S08 checkpoint

On the same Windows/Python 3.12 host, the full suite passed with **323 passed,
2 expected skips** against each of PostgreSQL 17.11 and 18.6, including SQLite
in both runs. The SQLite-only run passed 189 tests with one expected skip.
After adding final tests for capped diagnostics and binary revision ordering,
the focused migration suite passed **39 tests per PostgreSQL version**, including
SQLite. No production code changed after the full-suite runs. Ruff and
`examples/schema_evolution.py` passed.

S08 adds declaration preflight with stable errors, consistent binary revision
ordering, idempotent repeated constraint declarations, and deterministic
violations identifying storage, path, rule and affected IDs. Uniqueness
diagnostics include complete duplicate-group counts with a 100-row report cap.

Tests cover full-request rollback after checksum drift and invalid existing
data, physical schema equality after failed installation, required/primitive/
unique enforcement using a direct sqlite3 connection, missing/null and numeric
type distinctions, quoted object keys, arrays, and metadata version refusal.
The PostgreSQL proof rejects evolution before any schema mutation across the
whole request; it remains creation-only.

Process exits at trigger creation, index creation, metadata updates, revision
recording and commit recover to the correct transaction boundary. Every case
passes integrity/FK checks and a successful migration retry. A separate-process
writer is rejected while validation holds the SQLite write lock. These are
process-crash and lock tests, not power-loss simulations.

The new executable example demonstrates validation, explicit data repair,
installation, replay and raw-SQL rejection. CI is configured to run it across
the OS/Python matrix; that configuration does not establish executed CI results.
Storage remains format 2 and core dependencies are unchanged. S08 is complete;
Gate B remains open for the tracked UUIDv7 decision and final API review.

## S09 checkpoint

Full SQLite plus PostgreSQL 17.11 and 18.6 runs passed **342 tests with 2 expected
skips per run** on the same Windows/Python 3.12 host. The final focused inspection
and recovery suite passed **27 tests**, including additional backup error handling
and journal-preservation assertions. Ruff and `examples/recovery.py` passed.

SQLite now compares managed SQL structures with declarations recreated in an
isolated empty database, validates mappings and migration checksums, and checks
existing data against declared constraints. Tests alter/remove tables, columns,
indexes and triggers, replace trigger bodies, introduce unexpected triggers,
damage metadata, and restore triggers over invalid data. Checks report failures
without repairing source storage. Column order differences introduced by
canonical metadata encoding do not cause false failures.

Backups use SQLite's backup API and convert only the detached artifact to DELETE
journal mode before structural validation and no-overwrite publication. Tests
verify live WAL sources retain their mode, temporary sidecars are absent after
ordinary completion/failure, and binary values, versions, links and external
tables survive restoration. Restored writes are independent of the source.
Damaged artifacts cannot be published through the validated backup path.

CLI tests cover read-only inspection/checks, missing source paths, invalid
arguments, failed checks, backup restoration and filesystem errors without
tracebacks. Publication races preserve the competing destination. Process
termination during copying and before/after publication leaves either no
destination or a complete validated artifact; retry/reopen checks pass. Crashes
can leave abandoned partial files, as documented. These are process-crash tests,
not power-loss guarantees.

PostgreSQL checking remains explicitly limited to metadata/checksum and table
existence checks. Full native schema verification and physical backup are not
claimed for that proof adapter. Storage format and core dependencies are unchanged.
CI now includes the recovery example; actual OS/Python matrix execution and
release qualification remain outstanding. S10 logical-artifact hardening is next;
Gate B's UUIDv7 decision/API review remain open.
