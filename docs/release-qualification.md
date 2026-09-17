# v0.1.0rc1 qualification

This is a review candidate, not a supported release. Gate C remains open until
the complete OS/Python matrix has passing evidence, including macOS. No Git remote
is configured locally, so remote CI cannot yet be dispatched. No package is
published automatically.

## SQLite capability boundary

SQLite 3.38 is a version floor, not a sufficient capability guarantee. Open now
verifies escaped object-key extraction before changing connection configuration.
Linux's tested system SQLite 3.46.1 silently missed quoted keys, causing query
and constraint failures; it is rejected with `UnsupportedError`. SQLite 3.49.1
passes. Use a Python build with a capable SQLite library; qualification also
tests uv-managed builds. There is no callback or degraded-constraint fallback.
Report the loaded SQLite version rather than inferring it from Python's version.

Writable WAL has a separate fail-closed boundary following SQLite's WAL-reset fix:
3.51.3+, or the fixed 3.50.7 and 3.44.6 backport lines. New files fall back to DELETE
on an otherwise compatible unqualified runtime. Explicit WAL and existing writable
WAL files are rejected with upgrade/DELETE guidance. This policy was added after the
recorded rc1 artifact qualification; those artifact reports are historical evidence
and do not qualify the new API. See [SQLite runtime configuration and
maintenance](sqlite-runtime.md).

## UUIDv7 decision

Generated document/table IDs use RFC 9562 UUIDv7: 48-bit Unix milliseconds and
74 cryptographically random bits, with fixed version/variant bits. One stateless,
dependency-free implementation serves Python 3.12–3.14. Existing UUIDv4 and custom
text IDs remain valid; no stored records are rewritten.

IDs group by wall-clock millisecond. They do not guarantee ordering within a
millisecond, during clock rollback, or by commit time. Use an explicit application
sequence when needed. Python 3.14's native generator uses different counter
semantics; MeldDB keeps one behavior across its Python versions. The local
10,000-row UUIDv4/v7 index sample showed essentially equal time and page counts.
Adoption provides timestamp grouping, not a demonstrated speedup at this scale.

Sources: [RFC 9562 section 5.7](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7),
[Python UUID documentation](https://docs.python.org/3.14/library/uuid.html).

## API review and remaining gates

Review covers ownership, rollback/failure poisoning, detached values, bounded
queries/traversal, raw SQL, migrations and format/backend boundaries. The design
retains plain data and explicit persistence without object lifecycle machinery.
Gate A established scoped product value. The UUID decision is resolved; Gate B
requires the final capability-gated candidate's conformance evidence. Gate C
additionally requires every promised platform and clean-install check.

## Reproduction

```console
uv run --extra test --extra postgres pytest
uv run --extra test ruff check .
uv build
uv run python validation/qualify.py dist/melddb-0.1.0rc1-py3-none-any.whl dist/melddb-0.1.0rc1.tar.gz
uv run python validation/release_performance.py
uv run python validation/traversal_scale.py
```

The runner installs each artifact with no dependencies into a fresh environment,
verifies import location, and runs every example. It then adds test-only tooling
and runs copied tests outside the checkout, including installed-package recovery
subprocesses. Reports record Python, SQLite, artifact hashes and platform.
Artifacts remain local under `dist/`; publication is separate.

Performance fixtures cover 10,000 documents, 100 indexed lookups, 10,000 batched
activity writes and 50,000 edges. Equality compilation now matches the managed
partial expression index; an EXPLAIN assertion protects against full scans.
Single samples compare the checked API with simpler direct-driver implementations;
they establish no universal latency guarantee.

CI includes OS/Python, PostgreSQL 17/18, clean artifacts, examples, the TypeScript
reader and performance correctness. Configured jobs are not executed evidence.
Process-crash tests do not simulate every power-loss/filesystem failure. See
the separate validation and platform reports for actual outcomes.
