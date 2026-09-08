# MeldDB implementation and validation plan

## Product contract

Build a Python SDK that combines ordinary SQL tables, JSON documents, and
directed persistent relationships. Plain data in, plain data out; all database
I/O is explicit. No Coffy compatibility or import requirement.

First release: SQLite SDK for desktop applications, CLI tools, and small local
services; experimental PostgreSQL proof. Python 3.12–3.14, synchronous API,
Windows/macOS/Linux. Built-in sqlite3 with SQLite 3.38+; optional Psycopg 3
against PostgreSQL 17/18. No third-party core runtime dependency. Tests use
Pytest/Hypothesis; SQLAlchemy Core is only a comparison baseline.

Keep public operations, behavioral rules, backend adapters, and storage
utilities distinct. No process-global connection registry or plugin framework.

## Locked behavior

- Handle lookup does not create storage; first document insert may do so.
  Managed tables and directed relationships require explicit declarations.
- Documents return id/version/body envelopes. Replace replaces the full body.
  Conditional replace/delete raises ConflictError for stale versions.
- Managed tables use immutable text IDs (UUIDs by default) and text, int64,
  finite float, boolean, and bytes columns. Return detached dictionaries.
- Portable predicates: scalar equality/inequality, numeric comparison, scalar
  membership, Boolean combinations, explicit missing/null, object-key paths.
  Do not coerce strings, numbers, and booleans. JSON integers are bounded by
  the exact JavaScript integer range; Unicode excludes NUL/surrogates.
- Bounded limit/offset queries have deterministic ID tie-breakers and defined
  missing/null/case-sensitive ordering. Raw SQL retains driver syntax; cursor
  metadata determines whether results exist, including WITH and RETURNING.
- Relationships have fixed source/target storage, unique endpoint pairs,
  optional JSON properties, and restrict (default) or cascade deletion.
  References belong to one database handle and declared endpoint storage.
- Traversal uses batched BFS in one read transaction, unique records/minimum
  depths, default depth one, default budgets 10,000 nodes/50,000 edges.
  Budget overflow raises; no silent partial result. Permit cycles/self-links.
- Standalone writes are atomic; explicit tx owns all operations. Failure
  poisons tx even if caught. Reject nested tx and ordinary db operations while
  tx is active. Expire tx handles, confine db handles to one thread, no retry.
- New SQLite storage: WAL, synchronous FULL, FK enforcement and five-second
  configurable busy timeout. Preserve existing external journal modes.
- Versioned checksummed migrations support creation, indexes, required fields,
  primitive types and uniqueness. Validate existing data under a write-safe
  transaction; structured violations; atomic failure. Enforce constraints in
  SQL without Python callbacks. Null/missing do not participate in uniqueness.
- Inspection, structural checks, SQLite backup API, consistent logical exports
  with version/schema/records/edges/checksums and explicit binary encodings.
  List excluded external/native objects. Import only to new/empty storage;
  preserve IDs/versions, validate checksums/constraints/relationships.

## Delivery sequence and current status

Existing code covers portions of every slice. Implementation presence alone
does not close a slice or gate.

| Slice | Dependency | Current evidence and remaining work |
| --- | --- | --- |
| S01 persistent documents | None | CRUD, reopen, isolation, detached values tested; expand lifecycle boundary review |
| S02 atomic mixed workflow | S01 | Injected rollback after document/link/row tested on both adapters |
| S03 PostgreSQL proof | S02 | 17/18 shared tests now run locally; CI jobs and matrix added; harden edge cases as shared contract expands |
| S04 comparative product proof | S03 | Gate A passed for the documented workload: 27 shared comparison tests, complete setup/helper metrics; see gate-a.md |
| S05 document queries | S04 Gate A | Implemented and shared conformance added: operators, ordering, paging, object paths, conditional writes and numeric boundaries; see queries-and-crud.md |
| S06 relational CRUD | S04 Gate A | Implemented and shared conformance added: all scalar types, projection, CRUD, validation and existing SQL; executable address-book example |
| S07 traversal | S05/S06 | Shared graph/property tests, snapshot checks and 10,000-document/50,000-edge driver comparison pass; see relationships.md and s07-scale-results.json |
| S08 schema evolution | S05/S06/S07 | Validated declaration preflight, structured violations, raw-SQL enforcement, write-safe installation, checksum/order rollback and interrupted evolution/retry; see migrations.md |
| S09 inspection/recovery | S08 | Structural/constraint/checksum checks, read-only CLI, validated standalone backups and publication-crash recovery tested; see inspection-and-recovery.md |
| S10 logical portability | S09/S03 | Strict artifact validation, atomic import/recovery, shared int64/binary fixture, PostgreSQL round trip and lossless TypeScript checksum reader tested; see logical-format.md |
| S11 release qualification | S01–S10 | Local alpha artifacts only; actual OS/Python matrix runs, installation, performance, docs and evidence pending |

### Gate A — product value

Continue API expansion only after settings work without classes/migrations/
sessions, and mixed workflows need no identity registry, edge SQL, or transaction
coordination helpers. Apply identical correctness tests to direct drivers plus
helpers, SQLAlchemy Core, and MeldDB. Include setup/helpers in the comparison,
SQL inspection, and a query outside the portable subset. If the mixed workflow
does not meaningfully improve on driver helpers, present evidence and reassess.
Gate A PASSED for the demonstrated workload; see gate-a.md and gate-a-results.json.
This does not establish full SDK equivalence, performance or production usability.

### Gate B — API freeze

After S08, freeze v0.1 only once lifecycle, query, migration, raw-SQL, and backend
proof tests pass. All current APIs remain experimental. Gate B is OPEN.
Evaluate UUIDv7 for SDK-generated record IDs before this freeze, including
Python 3.12–3.14 support and dependency-free generation. Existing IDs must remain valid.

### Gate C — release qualification

After S11, designate SQLite supported, publish PostgreSQL capability limits,
and build reviewable release artifacts. Package publication is a separate
action. Gate C is OPEN; nothing in this repository auto-publishes packages.

## Evidence still required

- Language-neutral conformance fixtures and property tests for JSON round trips,
  predicates and graph reachability, injection attempts, stale versions, IDs,
  missing/null, numeric bounds, booleans, and unusual names.
- Deterministic pagination; ownership/expired/nested transaction failures;
  writer contention across processes; raw SQL writes/RETURNING/CTEs.
- Process termination before/after commit and during migrations, import, backup.
  Describe these as process-crash tests, not power-loss simulations.
- All five workloads: settings, address book, dependencies, structured activity
  retention, existing external SQL. Mixed workflow includes reopen, failure
  rollback, backup restoration and logical transfer. Run examples in CI.
- 10,000 documents and 50,000 edges; bulk insertion, indexed lookup, traversal,
  batched activity vs direct-driver baselines. Record hardware/dependencies;
  reject per-record query loops and full-history rewrites.
- Clean wheel/sdist installation on all OSes and Python 3.12–3.14, report loaded
  SQLite version, complete docs and assembled-system recovery checks.

## Later milestones

Complete PostgreSQL and offline cutover; add libSQL local/remote then replicas
as a distinct consistency mode; production TypeScript SDK; one named ORM's
transaction integration; evaluate PGlite. Async, sync, encryption management,
event subscriptions, graph analytics/Cypher, broad schemas, undirected/parallel
edges, callbacks, inheritance, lazy loading, tracked models, identity maps,
automatic flushing and automatic schema diffing are outside this milestone.

Add capabilities only when they simplify demonstrated workflows without hidden
persistence behavior. Next priority: resolve the UUIDv7 decision and review Gate B,
then S11 release qualification and assembled-system evidence. S08's passing migration
tests alone do not freeze the public API.
