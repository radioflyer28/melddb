# Design

## Context

See proposal.md and MeldStore's PostgreSQL provider verification for the failing
baseline. Both SQL entry points use one regular-expression guard; driver errors
are already translated by the backend adapter.

## Goals / Non-Goals

Close the observed ownership and error-classification gaps without adding a SQL
parser dependency, rewriting application SQL, or changing transaction retry policy.
Raw SQL remains a trusted application escape hatch, not an authorization sandbox
for arbitrary routines, extensions, or privileged administrative operations.

## Decisions

Scan only the leading command token. Skip whitespace, empty leading statements,
line comments and block comments; nest block comments for PostgreSQL only.
Recognize identifier boundaries independently of punctuation. Reject malformed
leading comments before execution. Leave the remaining statement unchanged, so
quoted bodies, trigger programs and parameters retain driver semantics. The
drivers continue enforcing a single executable statement. Keep PostgreSQL session
controls in its dialect-specific denylist, including SQL-level prepared-statement
controls; driver-internal preparation remains available.

Do not classify all OperationalError instances as connection failures: PostgreSQL
uses that base for lock and serialization errors too. Preserve existing SQLSTATE
priority, then map connection classes, shutdown/session-expiry codes, and
SQLSTATE-less operational/interface failures. Do not alter transaction-finalization
logic or equate disconnection with confirmed rollback.

## Risks / Trade-offs

- Comment dialect mismatch could hide controls: exercise both actual engines,
  including SQLite non-nested comments and PostgreSQL nested comments.
- Overclassification could swallow BusyError: test lock/deadlock/serialization
  cases and retain their original driver causes.
- Trusted SQL can invoke application routines: engine read-only enforcement still
  applies; this guard is not a general SQL security boundary.

## Migration Plan

Run the complete MeldDB tests and live provider tests, commit the focused revision,
publish the branch, then update and qualify MeldStore's exact Git dependency.
Keep shared guarantees and owning-repository evidence linked. No database migration
or merge to main is required. A rollback must not claim the old pin meets the new
PostgreSQL provider contract.

References: [PostgreSQL lexical rules](https://www.postgresql.org/docs/17/sql-syntax-lexical.html),
[transaction modes](https://www.postgresql.org/docs/17/sql-set-transaction.html),
[Psycopg errors](https://www.psycopg.org/psycopg3/docs/api/errors.html).
