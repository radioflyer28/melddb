# Explicit constraint validation

`tx.validate_constraints()` checks pending constraints in a live write transaction
and returns `None`. It never commits, retries or reconnects. Failure poisons the
transaction even when caught. Ownership, read-only rejection and uncertain-outcome
quarantine apply as for other transaction operations.

PostgreSQL runs `SET CONSTRAINTS ALL IMMEDIATE` through the backend, forcing
deferred foreign keys, unique/exclusion constraints and constraint triggers.
Checks remain immediate for the rest of this transaction. SQLite runs
`PRAGMA foreign_key_check`; it does not change future constraint timing. SQLite
checks other supported constraints immediately already. This method is not a
whole-database integrity audit or a guarantee that later writes/commit will succeed.

For a dry run, execute the intended writes, validate, then raise an application
exception to roll back. Validation can execute deferred application triggers.
Transactional trigger effects roll back, but external side effects and PostgreSQL
sequence increments do not. Keep dry-run callbacks free of external side effects.

Raw/bulk SQL still rejects transaction/session controls. Applications should not
wrap rejected controls in anonymous blocks/functions to bypass that boundary.
PostgreSQL remains experimental; downstream applications qualify independently.

Qualification (2026-11-11): PostgreSQL 17.11 plus SQLite focused provider/control tests: 96 passed, 22 backend-specific skips. Full SQLite suite: 378 passed, 25 skips. Ruff and strict change validation passed. Windows/Python 3.13; no production support expansion. The disposable PostgreSQL container was removed.
