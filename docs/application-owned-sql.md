# Application-owned SQL tables

MeldDB supports ordinary application-owned SQL tables in the same database as
MeldDB-managed documents, tables, and relationships. An application-owned table
remains ordinary database schema: MeldDB can query and mutate it through explicit
SQL, but does not adopt its shape, track its records, or migrate it.

`db.inspect()` reports these tables under `external_tables`. Here, "external"
means external to MeldDB's managed schema; the table can still live in the same
SQLite database file or PostgreSQL schema.

## Ownership contract

| Concern | Owner |
| --- | --- |
| Database connection, explicit transaction, parameterized SQL | MeldDB |
| Application table DDL, indexes, triggers, checks, and foreign keys | Application |
| Application migration IDs, ordering, history, and compatibility policy | Application |
| Managed documents, tables, relationships, and managed migration history | MeldDB |
| SQLite physical database backup | MeldDB backup API |
| External files, object-store payloads, and complete application recovery | Application |

MeldDB has no generic application-table migration runner or automatic schema
diff. An application may execute its own DDL through `db.sql()` or `tx.sql()` and
record its own migration history, but MeldDB's migration ledger covers only
managed declarations.

## Compose work in one transaction

Use the transaction-owned handle for both managed operations and application SQL:

```python
import melddb
from melddb import Migration, schema

with melddb.open("project.db") as db:
    db.sql("CREATE TABLE IF NOT EXISTS sensors(id TEXT PRIMARY KEY)")
    db.sql(
        "CREATE TABLE IF NOT EXISTS recordings("
        "id TEXT PRIMARY KEY, sensor_id TEXT NOT NULL REFERENCES sensors(id))"
    )
    db.migrate(Migration("001", (schema.collection("notes"),)))

    with db.transaction() as tx:
        tx.sql("INSERT INTO sensors VALUES (?)", ("sensor-1",))
        tx.sql("INSERT INTO recordings VALUES (?,?)", ("recording-1", "sensor-1"))
        tx.collection("notes").insert(
            {"recording_id": "recording-1", "state": "ready"}, id="note-1"
        )
```

All three writes share one commit outcome. If a foreign key, uniqueness rule,
check, trigger, or managed operation fails, the transaction cannot continue and
the scope rolls back. Catch an operation error outside the transaction scope;
MeldDB does not retry it.

SQL remains driver-dialect SQL. SQLite uses `?` parameters; PostgreSQL uses `%s`.
Keep portable application behavior in application code and use backend-specific
DDL where the database dialects differ.

## Relationships and private managed layout

Application-owned tables may use ordinary foreign keys and junction tables among
themselves. MeldDB enables SQLite foreign-key enforcement on every connection and
uses the database's constraint behavior inside explicit transactions. The
application remains responsible for defining, migrating, and validating those
relationships.

Do not create application foreign keys to MeldDB's physical managed tables.
Physical names shown by `db.inspect()` are diagnostic mappings, not stable public
identities or a portable schema contract. Use application-owned identifiers and
tables for authoritative cross-domain relationships.

## Inspection and validation limits

`db.inspect()` separates managed objects from `external_tables`; it does not
register external tables as managed. `db.check()` does not rewrite any records.
On SQLite it runs native integrity and foreign-key checks, then validates MeldDB's
managed metadata and generated structures. It does not know the application's
expected columns, indexes, triggers, migration version, or domain rules.

An `ok` check therefore means the database passed those documented checks, not
that an application-owned schema matches the application's model. Applications
should run their own schema/version and domain validation in addition to
`db.check()`.

## Backup and logical transfer are different

`db.backup(new_path)` is a SQLite physical backup. It captures one consistent,
committed snapshot of the complete SQL database, including application-owned
tables, records, indexes, views, triggers, constraints, and foreign-key/junction
relationships. It refuses to overwrite an existing destination.

That database snapshot is not necessarily a complete application backup. If the
application owns files, S3 objects, secrets, or other state, it must coordinate
their lifecycle and recovery with the database snapshot.

`db.export(new_path)` is a managed logical transfer artifact. It contains only
MeldDB-managed schema, migration history, and data. It reports application-owned
tables in `exclusions.external_tables` and native objects in
`exclusions.native_objects`; `db.import_into()` does not recreate them. Use a
physical SQLite backup when application-owned SQL must be preserved exactly, or
provision and restore that schema through the application's own recovery process.

## Backend status

SQLite is the supported target for this contract. PostgreSQL remains an
experimental portability proof: configured tests exercise driver-dialect SQL and
mixed transaction behavior, but structural checking is not SQLite-equivalent and
MeldDB's physical backup API is unavailable. Consult the
[backend capability matrix](backend-matrix.md) before relying on PostgreSQL.
