"""Plain-value collections and deliberately modest relational CRUD."""
import json
import math

from .backend import quote
from .database import physical
from .errors import ConflictError, NotFoundError, ValidationError
from .identifiers import new_id
from .query import compile_predicate, ordering
from .values import Ref, encode, text

TYPES = {"text", "integer", "float", "boolean", "bytes"}


def validate_column(kind, value):
    if kind not in TYPES:
        raise ValidationError(f"Unsupported column type {kind}")
    if value is None:
        return
    if kind == "float":
        try:
            valid_float = type(value) in (int, float) and math.isfinite(float(value))
        except OverflowError:
            valid_float = False
        if not valid_float:
            raise ValidationError("Expected a finite floating-point value")
        return
    valid = ((kind == "text" and isinstance(value, str)) or
             (kind == "integer" and type(value) is int and -(2**63) <= value < 2**63) or
             (kind == "float" and type(value) in (int, float) and math.isfinite(value)) or
             (kind == "boolean" and type(value) is bool) or
             (kind == "bytes" and isinstance(value, bytes)))
    if not valid:
        raise ValidationError(f"Expected {kind}, got {type(value).__name__}")
    if kind == "text":
        text(value)


class Store:
    kind = None

    def __init__(self, scope, name):
        self.scope, self.db, self.name = scope, scope._db, name
        self.physical = physical(name)
        self.sqlname = quote(self.physical)

    def _spec(self):
        return self.db._spec(self.name, self.kind)

    def ref(self, record):
        ident = record["id"] if isinstance(record, dict) else record
        return Ref(self.name, text(ident), self.db._owner)

    def _decode(self, row, spec):
        if self.kind == "collection":
            body = row["body"]
            return {"id": row["id"], "version": row["version"],
                    "body": json.loads(body) if isinstance(body, str) else body}
        for col, kind in spec["columns"].items():
            if col in row and row[col] is not None:
                if kind == "boolean":
                    row[col] = bool(row[col])
                elif kind == "bytes":
                    row[col] = bytes(row[col])
                elif kind == "float":
                    row[col] = float(row[col])
        return row

    def get(self, ident):
        with self.scope._operation():
            text(ident)
            try:
                spec = self._spec()
            except NotFoundError:
                if self.kind == "collection":
                    return None
                raise
            rows = self.db._backend.execute(f"SELECT * FROM {self.sqlname} WHERE id=?", (ident,))[0]
            return self._decode(rows[0], spec) if rows else None

    def find(self, where=None, *, order_by=None, descending=False, limit=100, offset=0,
             columns=None):
        with self.scope._operation():
            if (type(limit) is not int or not 1 <= limit <= 10000 or
                    type(offset) is not int or not 0 <= offset <= 2**63-1):
                raise ValidationError("limit must be 1..10000 and offset 0..2**63-1")
            if type(descending) is not bool:
                raise ValidationError("descending must be a boolean")
            absent = False
            try:
                spec = self._spec()
            except NotFoundError:
                if self.kind == "collection":
                    spec = {"op": "collection", "name": self.name}
                    absent = True
                else:
                    raise
            expr, params = compile_predicate(where, spec, self.db._backend.pg)
            order = ordering(order_by, spec, self.db._backend.pg, descending)
            projection = "*"
            if columns is not None:
                if self.kind != "table" or not isinstance(columns, (list, tuple)) or not columns or any(
                    not isinstance(c, str) or c not in {"id", *spec["columns"]} for c in columns
                ):
                    raise ValidationError("Invalid projection")
                projection = ",".join(quote(c) for c in columns)
            if absent:
                return []
            rows = self.db._backend.execute(
                f"SELECT {projection} FROM {self.sqlname} WHERE {expr} ORDER BY {order} LIMIT ? OFFSET ?",
                (*params, limit, offset))[0]
            return [self._decode(row, spec) for row in rows]

    def delete(self, ident, *, expected_version=None):
        with self.scope._operation(write=True):
            text(ident)
            params = [ident]
            condition = "id=?"
            if expected_version is not None:
                if (self.kind != "collection" or type(expected_version) is not int or
                        not 1 <= expected_version <= 2**63-1):
                    raise ValidationError("Expected a positive document version")
                condition += " AND version=?"
                params.append(expected_version)
            try:
                self._spec()
            except NotFoundError:
                if self.kind != "collection":
                    raise
                if expected_version is not None:
                    raise ConflictError("Document missing or version changed") from None
                return False
            rows, _ = self.db._backend.execute(
                f"DELETE FROM {self.sqlname} WHERE {condition} RETURNING id", params)
            if not rows and expected_version is not None:
                raise ConflictError("Document missing or version changed")
            return bool(rows)


class Collection(Store):
    kind = "collection"

    def insert(self, body, *, id=None):
        with self.scope._operation(write=True):
            body = encode(body, object_only=True)
            ident = new_id() if id is None else text(id)
            try:
                spec = self._spec()
            except NotFoundError:
                from .migrations import create
                spec = {"op": "collection", "name": self.name}
                create(self.db, spec)
            rows = self.db._backend.execute(
                f"INSERT INTO {self.sqlname}(id,version,body) VALUES (?,1,?) RETURNING *",
                (ident, body))[0]
            return self._decode(rows[0], spec)

    def replace(self, ident, body, *, expected_version=None):
        with self.scope._operation(write=True):
            text(ident)
            body = encode(body, object_only=True)
            condition = "id=? AND version<9223372036854775807"
            params = [body, ident]
            if expected_version is not None:
                if type(expected_version) is not int or not 1 <= expected_version <= 2**63-1:
                    raise ValidationError("Expected a positive document version")
                condition += " AND version=?"
                params.append(expected_version)
            try:
                spec = self._spec()
            except NotFoundError:
                if expected_version is not None:
                    raise ConflictError("Document missing or version changed") from None
                raise
            rows = self.db._backend.execute(
                f"UPDATE {self.sqlname} SET body=?,version=version+1 WHERE {condition} RETURNING *",
                params)[0]
            if not rows:
                if expected_version is not None:
                    raise ConflictError("Document missing or version changed")
                if self.db._backend.execute(f"SELECT id FROM {self.sqlname} WHERE id=?", (ident,))[0]:
                    raise ConflictError("Document version counter exhausted")
                raise NotFoundError(ident)
            return self._decode(rows[0], spec)


class Table(Store):
    kind = "table"

    def _values(self, row, spec):
        if not isinstance(row, dict) or any(c not in spec["columns"] for c in row):
            raise ValidationError("Unknown column or attempted primary-key mutation")
        for col, value in row.items():
            validate_column(spec["columns"][col], value)

    def insert(self, row, *, id=None):
        with self.scope._operation(write=True):
            spec = self._spec()
            self._values(row, spec)
            ident = new_id() if id is None else text(id)
            cols = ["id", *row]
            values = [ident, *(float(v) if spec["columns"][c] == "float" and v is not None else v
                               for c, v in row.items())]
            rows = self.db._backend.execute(
                f"INSERT INTO {self.sqlname} ({','.join(quote(c) for c in cols)}) "
                f"VALUES ({','.join('?' for _ in cols)}) RETURNING *", values)[0]
            return self._decode(rows[0], spec)

    def update(self, ident, changes):
        with self.scope._operation(write=True):
            text(ident)
            spec = self._spec()
            self._values(changes, spec)
            if not changes:
                raise ValidationError("An update requires at least one column")
            rows = self.db._backend.execute(
                f"UPDATE {self.sqlname} SET {','.join(quote(c)+'=?' for c in changes)} "
                "WHERE id=? RETURNING *", (*(float(v) if spec["columns"][c] == "float" and v is not None else v
                                            for c, v in changes.items()), ident))[0]
            if not rows:
                raise NotFoundError(ident)
            return self._decode(rows[0], spec)
