# Tasks

## 1. Runtime Policy and Journal Configuration

- [x] 1.1 Add focused tests for the WAL safety allowlist, backported fixed versions, rejected writable-WAL runtimes, and explicit DELETE fallback; verify the new tests fail against the current implementation for the expected reasons.
- [x] 1.2 Implement the adapter-owned SQLite safety decision and verify capability failures close acquired connections before application or managed writes occur.
- [x] 1.3 Add the validated `journal_mode` open keyword for preserve/WAL/DELETE behavior across new, existing, read-only, and in-memory databases; verify effective mode and translated lock/VFS failures with focused tests.

## 2. Runtime Reporting

- [x] 2.1 Implement `Database.sqlite_runtime()` as a detached plain-data report of effective live settings and named capabilities; verify mutation of a returned report cannot affect the database or later reports.
- [x] 2.2 Add SQLite, in-memory, read-only, and PostgreSQL rejection tests for runtime reporting; verify requested values are never substituted for effective connection values.

## 3. Explicit Maintenance

- [x] 3.1 Add tests for optimize and full-analysis statistics actions, including persistent planner statistics and translated lock/I/O failures; verify default maintenance is bounded and reports its selected action.
- [x] 3.2 Implement validated statistics maintenance without exposing raw connections; verify `None`, `optimize`, and `analyze` selections produce the specified structured sections.
- [x] 3.3 Add checkpoint tests for PASSIVE partial progress, FULL/RESTART/TRUNCATE busy outcomes, completed truncation, and the no-WAL `-1/-1` case; verify normalized results distinguish busy, incomplete, and inactive WAL states.
- [x] 3.4 Implement checkpoint maintenance and combined `maintain_sqlite()` results; verify read-only, in-memory, PostgreSQL, cross-thread, and active-transaction calls fail before unsupported SQLite I/O.

## 4. Documentation and Consumer Boundary

- [x] 4.1 Document journal persistence, default compatibility behavior, effective-setting reports, WAL safety versions, maintenance costs, and cross-process coordination limits; verify examples use only public APIs and no private backend connection.
- [x] 4.2 Update the backend capability matrix and release-qualification evidence, and verify claims distinguish implemented SQLite behavior from PostgreSQL and from untested runtimes.
- [x] 4.3 Review the shared `metadata-provider-contract` and record whether a separate shared-store delta is required before MeldStore updates its pinned MeldDB revision; verify no MeldStore implementation is changed in this MeldDB change.

## 5. Verification

- [x] 5.1 Run `uv run --extra test pytest` and verify the complete SQLite and optional configured PostgreSQL suites pass without weakening existing transaction, backup, or raw-SQL tests.
- [x] 5.2 Run `uv run --extra test ruff check .` and verify the dependency-free core and supported Python-version constraints remain satisfied.
