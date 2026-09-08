# Gate A — comparative product proof

Decision: PASS for the demonstrated settings and mixed-data workload. Continue
to S05/S06 conformance work. This is a product-value gate, not API freeze or
release qualification. The comparison supports keeping the current small
relational facade; it does not justify adding object mapping or query machinery.

## Reproduce

```console
uv run --extra test pytest tests/test_comparison.py
uv run --extra test python validation/comparison.py --output docs/gate-a-results.json
```

The machine-readable results in [gate-a-results.json](gate-a-results.json)
were produced on Windows 11, Python 3.12.10, SQLite 3.49.1 and SQLAlchemy 2.0.52.
The implementations and every helper live in
[comparison.py](../validation/comparison.py). The common verifier runs in both
the CLI report and [the tests](../tests/test_comparison.py).

## Workload and identical correctness assertions

Settings is a separate function for each implementation. MeldDB's function
needs no application-defined classes, migrations or sessions. The mixed adapter
class only standardizes the comparison harness; it is not required for settings.

The mixed workflow writes two UUID-identified documents, connects them, then
adds an activity row in one explicit transaction. All implementations use
foreign keys, restrict deletion, unique endpoint pairs, a JSON object check,
WAL on new files, synchronous FULL and a five-second busy timeout. Only fixed
trusted table names are interpolated; application values use parameters.

For each implementation the verifier commits an initial batch, then checks:

1. Rollback after each of the four writes.
2. Rollback for a duplicate link.
3. Rollback for a missing endpoint.
4. Rollback for deletion of a linked document under restrict policy.
5. Rollback even when the duplicate-link exception is caught inside the scope.

Every failure preserves the complete prior snapshot, including all links and
activity rows. Every case checks a JSON extraction/window-function SQL query
outside the portable predicate subset, closes/reopens storage, checks the same
snapshot, commits another batch and verifies endpoint identity/content.

Result: 24 mixed cases plus three standalone settings cases pass (27 tests).
Each mixed case includes successful commits, failure recovery, raw SQL and reopen.

## Complete application code inventory

| Measured source | MeldDB | sqlite3 + helpers | SQLAlchemy Core + helpers |
| --- | ---: | ---: | ---: |
| Mixed adapter, including setup/inspection/fault branches | 40 | 57 | 50 |
| Application helpers | 0 | 29 | 41 |
| Standalone settings function | 5 | 16 | 12 |
| Total nonblank lines | 45 | 102 | 103 |
| Total AST statements | 40 | 91 | 88 |

Counts use full AST source boundaries and include all methods, configuration
functions, the transaction failure guard and its error type. Shared helpers
are counted once per implementation, including when settings uses them too.
Imports and common verification/fault-injection infrastructure are excluded;
implementation-specific fault branches are included. Library internals, driver
internals and SQLAlchemy internals are excluded equally. These are application
glue measurements, not total system complexity or maintainability scores.
Line wrapping affects line counts; AST statement counts provide a second view.
No throughput/latency conclusion is drawn from these small fixtures.

## Concepts and correctness responsibilities

| Responsibility | MeldDB application | sqlite3 application | SQLAlchemy Core application |
| --- | --- | --- | --- |
| Connection durability/FKs | Open handle | Configure/check PRAGMAs | Configure DBAPI connection and engine |
| Schema | Creation migration declarations | DDL and schema setup transaction | MetaData, Table, Column, constraints |
| Document serialization | Plain dictionaries | JSON encode/decode | JSON column type |
| Record identity | SDK-generated IDs and references | UUID generation and parameter plumbing | UUID generation and insert values |
| Relationship correctness | Declared endpoints and connect | Edge table, FK and pair-key DDL | Edge table, ForeignKey and primary-key declarations |
| Atomic scope | Explicit transaction-owned handle | BEGIN/COMMIT/ROLLBACK helper | Engine.begin scope |
| Caught database failure | SDK marks transaction failed | Guard and end-of-scope check | Guard and end-of-scope check |
| SQL outside portable subset | inspect mapping plus sql | Driver execute | Core connection/text |

There is no custom identity registry or edge-maintenance SQL in the MeldDB
application. The activity insert remains a plain row insert; the table facade
does not require model classes, a session or relationship hydration.

## Interpretation and limits

The main benefit is a reusable correctness boundary for a mixed workflow.
SQLAlchemy Core already makes transactions and JSON columns straightforward;
MeldDB adds endpoint declarations, references and failure poisoning in one
small interface. The direct-driver solution remains quite reasonable for a
single application whose helpers are already written and maintained.

The baseline guard is necessary only for the locked contract that a caught
operation error must prevent commit. Applications that propagate every error
can omit that helper. MeldDB's advantage would be smaller under that different
contract. Engine creation uses SQLAlchemy's documented explicit BEGIN pattern
with sqlite3 implicit BEGIN disabled, so the comparison does not penalize Core
for a broken transaction configuration.

These baselines implement the compared workload, not MeldDB's entire SDK.
Document replacement/versioning, all portable predicates, reference ownership,
identity immutability through raw SQL, constraints beyond the declared fixture,
traversal, backup and logical transfer are not comparative claims here. The
MeldDB-specific conformance suite covers some of them separately. Stable error
names differ between implementations; assertions require their appropriate
constraint/abort categories and the same persisted result.

Gate A passes because the identical tested workflow removes meaningful setup
and error-handling glue while keeping transactions and SQL explicit. Broader
developer usability and representative production adoption remain unproven.
Gates B and C remain open.

References: [SQLAlchemy SQLite transaction control](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#enabling-non-legacy-sqlite-transactional-modes-with-the-sqlite3-or-aiosqlite-driver),
[Core connection scopes](https://docs.sqlalchemy.org/en/20/core/connections.html#connect-and-begin-once-from-the-engine).
