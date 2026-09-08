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
Windows/Python host matrix is incomplete. The full S04 comparison, performance
fixtures, schema-drift verification, adversarial artifact validation and release
qualification remain open in implementation-plan.md. Both database adapters
remain alpha; PostgreSQL remains experimental.

Container images used:

- postgres:17 — sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675
- postgres:18 — sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280

Images were used as test services with localhost-only ports and disposable
storage. No application database was modified by these runs.
