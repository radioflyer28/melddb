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
