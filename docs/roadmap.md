# MeldDB future roadmap

Preserved from the implementation plan and product discussion on 2026-09-10.
This is a direction and decision record, not authorization to resume development,
change release gates, configure a remote, or publish packages.

## Current checkpoint

S01-S10 are recorded in [the implementation plan](implementation-plan.md).
S11 has a local v0.1.0rc1 candidate and Windows/Linux qualification evidence;
macOS Python 3.12-3.14 qualification remains outstanding. Gate B passed for the
candidate API; Gate C remains open. SQLite is not yet designated supported and
PostgreSQL remains experimental. Keep the repository local and work paused until
requested. See [the handoff](next-session.md) and
[release qualification](release-qualification.md) for evidence and artifact hashes.

## Governing product contract

Plain data in, plain data out; all database I/O is explicit. Every capability must
simplify a demonstrated workflow without hidden persistence behavior. Keep the
core installation free of third-party runtime dependencies. MeldDB remains a
standalone application-data library; Cacheness is a prospective consumer.

## Original post-release milestones

These preserve the sequence in the original user-approved plan. Detailed scope
and acceptance plans must be established when each milestone is started.

| Order | Milestone | Intended completion evidence |
| --- | --- | --- |
| 1 | Complete PostgreSQL | Remaining portable operations, full managed-schema migration, shared conformance, and validated offline SQLite-to-PostgreSQL cutover; publish backend differences before changing support designation. |
| 2 | Add libSQL | Prove local and remote operation first; test replicas separately as a distinct consistency and connectivity mode. |
| 3 | Production TypeScript SDK | Use shared behavioral fixtures and logical format; the existing compatibility reader is not a supported SDK. |
| 4 | One named ORM transaction integration | Prove connection ownership, error propagation, and commit/rollback responsibility for one selected toolkit; no universal ORM layer. |
| 5 | Evaluate PGlite | Reuse the PostgreSQL behavior contract where supported; do not depend on future native bindings. |
| 6 | Evaluate advanced capabilities | Async, broader schemas, undirected/parallel edges, synchronization, and graph extensions require demonstrated workloads. |

The next release step remains obtaining macOS evidence and reviewing the candidate.
There is no automatic package publication. Current PostgreSQL limitations are in
[the capability matrix](backend-matrix.md), including schema evolution,
structural checks, and the limited logical-import proof.

## External consumer: Cacheness using MeldDB

Cacheness began as a caching library and evolved into a dual-role cache and blob
store. Its newer local checkout is an unfinished refactor, not a settled contract.
The user described the target as a generic blob-store backend with caching built
on top as a consumer. Cache-key derivation is a caching concern; the principal
MeldDB opportunity is queryable blob metadata.

Dependency direction: **Cacheness -> MeldDB**. The adapter, blob-store workflows,
and end-to-end integration tests belong in the Cacheness repository. MeldDB does
not depend on Cacheness or add Cacheness-specific APIs. The following consumer
context is preserved here to motivate general database requirements; it is not
an integration workstream in this repository.

The intended deployment path for that external consumer is:

| Layer | Start embedded | Transition to cloud storage |
| --- | --- | --- |
| Cacheness blob storage | Local files | S3 |
| MeldDB metadata | SQLite | PostgreSQL |
| Application | Stable logical identities and supported metadata operations | Same application behavior with different storage configuration |

Cacheness currently runs inside the consuming application, including when its
storage is remote. Avoiding an additional server/API was intentional. Preserve
that goal when evaluating integration; introducing a service is not a prerequisite.
Completing PostgreSQL is especially relevant to this workflow, but this discussion
does not change the first-release boundary or promote the experimental adapter.

## Cacheness-owned proposals to validate

The following are design recommendations from the discussion, not frozen API or
implementation commitments. Implementation belongs in Cacheness; any missing
general database capability should be evaluated separately for MeldDB:

- In Cacheness, introduce an optional MeldDB metadata backend after the generic blob-store
  contract stabilizes; do not redirect the unfinished Cacheness refactor around it.
- Cacheness owns serialization, compression, blob lifecycle, cache policies, and
  coordination between blob writes and metadata commits. MeldDB owns database
  persistence, supported queries, relationships, and explicit transactions.
- Separate logical blob identity from file paths and S3 locations. Preserve IDs
  during transfer. Generated UUIDv7 IDs are available, but do not replace explicit
  application IDs or deterministic cache keys merely to fit MeldDB.
- Use typed operational fields and flexible JSON metadata as workloads require.
  Add provenance/dependency relationships only when they simplify real use cases;
  do not require table/document/edge machinery for every ordinary blob operation.
- Allow blob and metadata backends to move independently, potentially through
  SQLite plus S3 as an intermediate deployment.
- Keep filtering in the database and batch hot operations. Avoid read/replace
  loops for counters or repeated per-record network queries. Raw SQL remains an
  explicit backend-specific option, not an arbitrary portability guarantee.
- Establish connection ownership compatible with MeldDB's thread-confined handles.
  Coordinate multiple processes through database constraints and explicit protocols,
  rather than relying solely on process-local locks.
- Define schema/client compatibility and explicit migration ownership. Give cleanup
  and reconciliation an explicit maintenance entry point or scheduled-job owner.
- Direct storage access suits trusted consumers. A future optional service can
  consume the same library if centralized authorization or policy becomes necessary.
  Library validation alone cannot constrain a client with direct storage credentials.

## Proposed acceptance in the Cacheness repository

These are prospective Cacheness acceptance criteria, not MeldDB release gates.
MeldDB owns its shared database conformance and logical metadata transfer tests;
Cacheness owns blob transfer, cross-store recovery, and application cutover.

1. Run one rich-metadata blob-store workflow against the existing Cacheness backend
   and the MeldDB adapter. Compare correctness, setup/helper code, SQL calls, and
   end-to-end performance, including network-sensitive access/update operations.
2. Cover insertion, metadata queries and updates without blob rewrites, replacement,
   namespace isolation, concurrent updates, reopen, and interrupted writes. Exercise
   relationships only in a demonstrated provenance/dependency workload.
3. Prove offline transfer: pause writes, copy blobs, verify checksums, transfer
   metadata and relationships, verify referenced blobs, then switch configuration.
   Preserve identities, versions, and supported query behavior. Never overwrite a
   working destination implicitly. Live migration and synchronization are separate.
4. Run the same application behavior against SQLite/files and PostgreSQL/S3 after
   transferring existing data. Two independent empty-backend demos are insufficient.
5. Document that a metadata transaction cannot atomically commit external blobs,
   and a MeldDB backup alone is not a complete Cacheness artifact backup. Define and
   test recovery across that boundary instead of promising cross-store atomicity.

Proceed only if integration removes meaningful application or metadata-management
code while preserving efficient ordinary operations. Keep the current backend or
limit integration to richer catalogs if the adapter merely wraps existing SQL.

## Comparison leads, not adoption decisions

The discussion identified Tiled, LanceDB/Lance, DiskCache, GridFS, and obstore as
useful comparisons. Tiled's separation of catalog, data sources, and physical
assets is worth studying, while its service architecture differs from Cacheness's
direct-access goal. LanceDB challenges the embedded metadata/blob story; DiskCache
is a simplicity baseline; obstore may be a blob-access building block. Recheck
current capabilities before making selection or performance claims.

- [Tiled architecture](https://blueskyproject.io/tiled/explanations/architecture.html)
- [Tiled direct client](https://blueskyproject.io/tiled/user-guide/direct-client.html)
- [LanceDB](https://github.com/lancedb/lancedb)
- [DiskCache](https://grantjenks.com/docs/diskcache/tutorial.html)
- [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [obstore](https://developmentseed.org/obstore/latest/)

## Boundaries retained

No tracked models, identity maps, automatic flushing, lazy loading, inheritance
mapping, persistence callbacks, or automatic schema diffing. Encryption management,
event subscriptions, Cypher/graph analytics, Coffy migration, and universal ORM
integration remain outside the current milestone. The roadmap does not imply that
any deferred capability is already implemented or approved for immediate work.
