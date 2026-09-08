# MeldDB contributor guidance

Preserve the product rule: plain data in, plain data out; all database I/O is
explicit.

- Do not introduce model base classes, tracked objects, identity maps,
  automatic flushing, or lazy loading.
- Keep the core installation free of third-party runtime dependencies.
- Treat SQLite as the supported backend and PostgreSQL as an experimental
  portability proof until its capability matrix is complete.
- Keep portable behavior in shared code and backend-specific SQL and
  transaction mechanics in adapters.
- Every capability must simplify a demonstrated application workflow without
  hiding persistence behavior.
- Run `uv run --extra test pytest` and `uv run --extra test ruff check .`
  before claiming a change is complete.
