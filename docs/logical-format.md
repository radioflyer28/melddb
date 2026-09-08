# Logical format 1 and portability proof

`db.export(new_path)` reads managed schema, migration history, documents, rows
and edges in one read transaction. `db.import_into(path)` restores them into an
empty database/schema in one write transaction. IDs, document versions and binary
values are preserved. A failed import leaves no partly installed schema or data.
There is no implicit overwrite, merge, or application-data conversion.

```console
uv run python examples/logical_transfer.py
node compat/read-export.ts tests/fixtures/logical-export.json
```

The example creates an artifact, imports it into fresh SQLite, closes/reopens it,
and checks the restored data. The committed fixture is imported by the shared
SQLite/PostgreSQL suite and read independently by TypeScript. PostgreSQL also
exports it back to SQLite in the proof tests. PostgreSQL remains experimental
and supports creation-only schemas/revisions; evolved constraints are rejected.
This does not establish general hosted cutover or a supported TypeScript SDK.

## Envelope and encodings

The UTF-8 JSON envelope contains exactly `payload` and `checksum`. The payload
contains `format: 1`, `objects`, `migrations` and `exclusions`.

Each object contains `schema`, `rows` and a row-array `checksum`. Schema uses
the ordinary declarative operations plus optional `constraints`. Collection rows
contain `id`, positive int64 `version` and object `body`; table rows contain `id`
and every declared column, using null where appropriate. Edge rows contain
`source_id`, `target_id` and object `properties`.

Binary columns use exactly `{"base64":"..."}` with canonical padded RFC-style
base64 (empty bytes use an empty string). Signed int64 columns and versions use
exact JSON integer tokens. Application document/property integers retain the
portable JavaScript-safe integer restriction. Larger exact application numbers
must be explicitly represented as strings, as in the regular API.

An ordinary JavaScript `JSON.parse` can round int64 values. The compatibility
reader preserves unsafe integer tokens as `bigint`; it never silently converts
them through a JavaScript number. The shared fixture includes both int64 limits,
maximum document version, binary data, float/exponent spellings and Unicode keys.

`migrations` contains ordered `{id, checksum, operations}` records. `operations`
is the canonical JSON string used by the migration checksum. Import validates
operation shape, order/uniqueness and agreement with the exported schema.
Implicit collections need not have a creation revision. Constraints are installed
after rows have been loaded and validated; endpoints precede relationships.

`exclusions.external_tables` lists tables omitted from the artifact.
`exclusions.native_objects` lists `{type, name}` descriptors for native indexes,
views, triggers and functions not copied verbatim. Managed indexes and triggers
are recreated from schema declarations; application native logic is not recreated.
Earlier format-1 alpha files used a descriptive string for native exclusions;
Python still accepts that representation. Physical backup is the mechanism for
preserving external SQL objects exactly.

## Checksums and canonical bytes

SHA-256 covers canonical UTF-8 JSON bytes: Python `json.dumps` with sorted keys,
no ASCII escaping, no non-finite numbers, and separators `,` and `:` without
whitespace. The envelope checksum covers the payload; each object checksum covers
its rows; a revision checksum covers its exact stored operations string.
This is the existing Python-defined format, not an implementation of RFC 8785.

Python verifies by canonical re-encoding. The TypeScript proof reader hashes the
original payload and row-array byte spans from canonical exporter output. This
preserves float spellings and Unicode key ordering across runtimes without
reserializing values. It rejects reformatted artifacts whose byte spans no longer
match, even when Python could canonicalize them successfully. Preserve the exact
exported bytes when using the compatibility reader.

Checksums detect corruption; they are not signatures or proof of provenance.
Python also validates schema, values, IDs, references, constraints and migration
history, so recomputing a checksum does not bypass those rules. TypeScript is a
bounded compatibility proof for canonical reading, checksums, identities,
relationships, versions, int64 and bytes; Python import remains the complete
supported validator.

## Validation and recovery

Import rejects duplicate JSON keys, non-finite constants, unknown envelope
fields, malformed schema/row encodings, duplicate storage names, out-of-range
versions/numbers, invalid IDs, duplicate records/edges and missing endpoints.
Binary decoding is strict. Schema/history disagreement or checksum drift fails.
Constraints use database enforcement; a final consistency check precedes commit.

The destination must have no user tables or other native objects; a view-only
SQLite database or PostgreSQL schema with relations/routines is not empty.
Select a fresh, exclusively owned destination. There is no overwrite mode.
Export validates managed consistency and portable values before publication.
Exports use temporary files and no-overwrite publication, as with backups.

Process-crash fixtures terminate during import, before commit, and after commit.
Reopening yields an empty destination or the complete imported state, and retry
works for uncommitted attempts. These are process-interruption tests, not
power-loss simulations. Files are currently loaded into memory; streaming and
resource-budgeted ingestion are outside this first format implementation.

The SQLite physical format remains 2 and logical format remains 1. No new core
dependency was added. Node is test/proof tooling only; core installation and
Python import do not require it.
