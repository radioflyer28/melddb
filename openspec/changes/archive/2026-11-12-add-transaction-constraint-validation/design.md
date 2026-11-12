# Design

## Context

Transaction._operation already enforces ownership, write intent, and failure
poisoning. PostgreSQL SET is deliberately unavailable through raw/bulk SQL.

## Goals / Non-Goals

Expose pending constraint validation without committing, retrying, reconnecting,
or permitting general transaction controls. No managed-table or blob concepts.

## Decisions

Add Transaction.validate_constraints(), returning None. Require a live write
transaction. Backend PostgreSQL executes SET CONSTRAINTS ALL IMMEDIATE, checking
deferred FK, unique/exclusion constraints and constraint triggers. It deliberately
leaves constraints immediate until transaction end; restoring deferred timing
could incorrectly defer originally immediate constraints. SQLite runs
PRAGMA foreign_key_check; immediate constraints are already checked by SQLite.
Do not claim SQLite changes future constraint timing. Existing error mapping,
poisoning and uncertain-outcome quarantine remain in force.

## Risks / Trade-offs

Deferred application triggers can execute during validation; their transactional
effects are rolled back by a dry run. External callback/sequence side effects are
not reversible. Successful validation is not a promise about later writes/commit.

## Migration Plan

Test both adapters, publish a source revision, then qualify and pin from MeldStore.
Keep the new method additive and leave raw control rejection unchanged.
