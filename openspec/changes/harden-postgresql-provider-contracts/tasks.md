# Tasks

## 1. Provider corrections

- [x] 1.1 Harden raw and bulk control-command validation; test rollback, pre-consumption rejection, comments, punctuation, ordinary SQL and engine-enforced reads on both backends, and document the boundary.
- [x] 1.2 Correct PostgreSQL disconnect classification; verify driver causes, constraint/busy classifications and unchanged structured outcomes and quarantine.

## 2. Integration evidence

- [x] 2.1 Run uv-based full tests and Ruff, live PostgreSQL tests and strict change validation; record the results.
- [ ] 2.2 Publish a focused provider revision and verify MeldStore's exact-pin PostgreSQL fixture, recording its revision and coordinating the shared safety contract.
