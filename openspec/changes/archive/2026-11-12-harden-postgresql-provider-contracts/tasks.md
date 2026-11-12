# Tasks

## 1. Provider corrections

- [x] 1.1 Harden raw and bulk control-command validation; test rollback, pre-consumption rejection, comments, punctuation, ordinary SQL and engine-enforced reads on both backends, and document the boundary.
- [x] 1.2 Correct PostgreSQL disconnect classification; verify driver causes, constraint/busy classifications and unchanged structured outcomes and quarantine.

## 2. Integration evidence

- [x] 2.1 Run uv-based full tests and Ruff, live PostgreSQL tests and strict change validation; record the results.
- [x] 2.2 Publish a focused provider revision and verify MeldStore's exact-pin PostgreSQL fixture, recording its revision and coordinating the shared safety contract.

## Evidence

Provider revision `bda3ca95fb6f5431e521162087bec97009074840` is published on
`codex/postgresql-provider-contracts`. MeldStore's unchanged PostgreSQL 17.11
fixture passed all 61 tests with no skips on 2026-11-11. The shared
`define-postgresql-provider-safety-contract` delta is synced to its canonical
metadata-provider contract. See `docs/postgresql-provider-contracts.md` for
upstream results and MeldStore's `docs/postgresql-provider-verification.md`
for exact-pin downstream evidence. No merge, release or archive is included.

Closeout 2026-11-12: completed tasks and canonical sync verified; archived after
MeldStore's integrated PostgreSQL/RustFS qualification (217 passed, zero skipped).
