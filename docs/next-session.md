# Paused checkpoint — 2026-09-08

User requested keeping MeldDB local and pausing here. Do not configure a remote,
push, publish, or start further qualification without a new instruction.

Repository: `C:/Users/akriz/code/melddb`. Candidate: `0.1.0rc1` in `dist/`.
S01–S10 implementation/validation slices are recorded in implementation-plan.md.
S11's local work is complete; macOS 3.12–3.14 evidence remains missing. Gate B
passed for the candidate API; Gate C remains open. SQLite is not yet designated
supported and PostgreSQL remains experimental. No packages have been published.

Final shared SQLite/PostgreSQL 17/18 suites: 407 passed, 2 expected skips each.
Wheel and sdist both passed clean installs, all examples, and installed-package
tests across Windows and Linux Python 3.12–3.14 (12 artifact/runtime combinations).
Exact versions/hashes are in s11-windows-*.json and s11-linux-*.json. Windows:
246 passed/1 skipped per artifact; Linux: 245 passed/2 skipped, including absent
Node. Ruff and performance correctness checks passed.

Changes include UUIDv7 defaults with old text IDs preserved, SQLite expression
index usage for document equality, and fail-fast SQLite JSON-path capability
verification. System SQLite 3.46.1 failed quoted-key semantics; tested Linux uses
uv-managed Python with SQLite 3.53.1. See release-qualification.md for limitations.

Artifacts (do not overwrite these without refreshing qualification evidence):

- Wheel SHA-256: `2818522f860d65681f32b11c1b9e32a60f8277b3a06bf5df2e6f2d4720248216`
- Sdist SHA-256: `0db1679aa30b1d027dd581969ebcdf071c438beb45402c59d2345acd6970d073`

All task-created containers have exited or been removed; Docker remains running.
Local caches and public CA certificates used for container TLS are ignored under
`.qualification/` and `.uv-cache/`, excluded from artifacts. These are not release
contents. No Git remote is configured, by the user's current preference.

When resumed, review the candidate and decide how to obtain macOS evidence. The
configured CI matrix can run once an authorized remote is supplied. Do not claim
Gate C complete solely from CI configuration or successful Windows/Linux tests.

## Future-work record — 2026-09-10

See [roadmap.md](roadmap.md) before planning later milestones. It preserves the
original backend/SDK roadmap and the Cacheness discussion, distinguishing agreed
goals from proposed designs. This documentation update does not resume development.

Ownership clarification: Cacheness depends on MeldDB and owns its adapter and
end-to-end integration in the Cacheness repository. MeldDB remains independent;
consumer context in roadmap.md does not authorize Cacheness integration here.

## Beta preparation — 2026-09-10

README.md now contains installation, runnable onboarding examples, ownership rules,
and recovery guidance. See beta-testing.md for controlled evaluation and reporting.
Feature work remains paused; no remote, publication, or artifact rebuild was done.
