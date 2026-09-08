# Document queries and relational CRUD (S05/S06)

All reads return detached values. Modifying a result never writes to storage.
All writes are explicit and share the same transaction-owned handles as
relationships. These interfaces remain alpha until Gate B.

## Documents

```python
import melddb
from melddb import field

with melddb.open("application.db") as db:
    docs = db.collection("packages")
    record = docs.insert({"name": "editor", "downloads": 50})
    matches = docs.find(field("downloads").gte(10),
                        order_by=field("downloads"), descending=True, limit=20)
    updated = docs.replace(record["id"], {"name": "editor", "downloads": 75},
                           expected_version=record["version"])
    docs.delete(updated["id"], expected_version=updated["version"])
```

Documents have an id/version/body envelope. Replacement discards the old body
entirely, including unmentioned fields and nested keys. There is no merge/patch.
get returns None for an absent ID, and find returns a list. Unconditional delete
returns False for an absent document, including an undeclared collection.
Unconditional replacement of an absent document raises NotFoundError.
Conditional replacement/deletion of an absent or stale document raises
ConflictError. Version inputs must be integers in 1..2**63-1; booleans are not
versions. An exhausted version counter raises ConflictError without mutation.

Only insertion implicitly creates collections. Invalid query arguments are
rejected even before collection storage exists. Raw SQL updates do not increment
managed document versions automatically.

## Predicates

field("metadata", "name") addresses nested object keys. A single key containing
a dot stays one key. Collection fields address the body, not envelope metadata.
Keys may be empty or contain quotes, whitespace, percent
signs or question marks. A key "0" addresses an object property; it never
indexes an array. Array traversal and wildcard paths are excluded.

| Expression | Meaning |
| --- | --- |
| field("x").eq(value), .ne(value) | Scalar equality/inequality within the scalar type |
| .gt(value), .gte(value), .lt(value), .lte(value) | Numeric comparison |
| .isin(values) | Membership; at most 500 supplied scalar values |
| .is_missing() | Document key absent (including a non-object ancestor) |
| .is_null() | Present JSON null, or SQL NULL for a table column |
| p & q, p \| q, ~p | Boolean conjunction, disjunction and complement |

Parenthesize Boolean expressions. Ordinary comparisons, including ne, do not
match null/missing values. Equality with None never matches; use is_null.
Strings, numbers and booleans are distinct; JSON integers/floats share the
numeric domain. ne also excludes values of other scalar types. Negation is
the Boolean complement of a predicate, so ~eq(1) includes null/missing and
other types. An empty membership list matches nothing. Objects and arrays
cannot be comparison operands.

Portable JSON accepts finite floats and integers within +/- (2**53-1). Encode
larger exact integers as strings. Exponent-form floats remain finite numeric
values when PostgreSQL JSONB renders them as integer literals: connection-local
JSON decoding maps out-of-range integer literals back to floating point.
This numeric policy also applies to JSON results from that handle's raw SQL;
SQL BIGINT values are unaffected. It does not provide exact-decimal storage.
Strings exclude NUL and unpaired surrogates.

## Ordering and pagination

find defaults to ascending ID order. With order_by, ties append ascending ID
order regardless of descending. Strings and IDs use case-sensitive binary/C
collation on SQLite/PostgreSQL. descending must be a bool and applies to the
specified sort field; default ID order stays ascending if no field is supplied.

Document type ranks always stay in this order: missing, null, boolean, number,
string, array, object. Within scalar ranks descending reverses values, while
ID ties remain ascending. Arrays and objects within their ranks are ordered
only by ID. Table NULLs come first in either direction. Shared expected results
live in tests/fixtures/ordering.json.

limit is an integer from 1 to 10,000 (default 100). offset is a nonnegative
signed-64-bit integer (default 0). These bounds validate driver inputs; high
offsets may still be expensive. Each find reads one snapshot; independent pages
can change under concurrent writes. Use one explicit transaction when pages
must observe the same data. Cursor pagination is deferred.

## Managed tables

```python
from melddb import Migration, schema

db.migrate(Migration("001", (
    schema.table("contacts", {"name": "text", "active": "boolean"}),
)))
contacts = db.table("contacts")
ada = contacts.insert({"name": "Ada", "active": False})
contacts.update(ada["id"], {"active": True})
names = contacts.find(field("active").eq(True), columns=["name"])
contacts.delete(ada["id"])
```

Tables require a declaration and use one immutable text ID, generated as a UUID
unless supplied explicitly via insert(..., id=...). Row dictionaries cannot
set/update the ID. update changes only the provided columns and requires at
least one change. Missing columns on insertion default to SQL NULL; require
constraints can tighten that. Unknown columns and malformed projections raise
ValidationError. get returns None for absent rows; update raises NotFoundError;
delete returns a bool. An undeclared table raises NotFoundError.

| Column type | Accepted non-null Python values |
| --- | --- |
| text | Unicode str without NUL/surrogates |
| integer | int in signed 64-bit range; not bool |
| float | int or float convertible to finite Python float; not bool |
| boolean | bool |
| bytes | bytes |

Float columns normalize numbers to float before binding on both backends,
including integer inputs outside the SQLite integer binding range. Values that
overflow float, NaN and infinity are rejected. This can round integers; use an
integer column for exact int64 data, or explicit strings for larger exact data.
Table predicates validate operands against their declared column type.

columns accepts a nonempty list/tuple of declared column names (or id), returning
dictionaries with just those scalar columns. No object hydration is performed.
Specialized values such as timestamps/decimals require explicit encoding.

## Existing SQL and runnable demonstration

Existing external tables stay external: query through sql with native driver
syntax (SQLite ?, Psycopg %s). inspect lists them. The managed table facade does
not adopt their schema. WITH queries and write statements with RETURNING return
rows because result presence is determined from cursor metadata.

```console
uv run python examples/query_crud.py .demo/queries
```

Use a fresh destination directory. The example demonstrates document queries,
stale-version handling, full address-book CRUD, persistence after reopening,
and access to a pre-existing SQL table. CI runs it on the OS/Python matrix.
