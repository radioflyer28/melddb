"""Connection ownership, explicit transaction scopes, and managed metadata."""
import hashlib
import json
import threading
import uuid
from contextlib import contextmanager

from .backend import Backend
from .errors import (
    MeldDBError,
    MigrationError,
    NotFoundError,
    OwnershipError,
    TransactionError,
    UnsupportedError,
    ValidationError,
)
from .values import encode, text

META = "_melddb_objects"
MIGRATIONS = "_melddb_migrations"
VERSION = "_melddb_format"
FORMAT_VERSION = 2


def physical(name):
    return "ad_" + hashlib.sha256(text(name).encode()).hexdigest()[:32]


class Scope:
    def collection(self, name):
        from .storage import Collection
        return Collection(self, text(name))

    def table(self, name):
        from .storage import Table
        return Table(self, text(name))

    def relationship(self, name):
        from .relationships import Relationship
        return Relationship(self, text(name))

    def sql(self, statement, params=()):
        with self._operation(write=True):
            # Raw SQL is an escape hatch, not a transaction-control API.
            import re
            cleaned = re.sub(r"/\*.*?\*/|--[^\n]*", " ", statement, flags=re.S).strip()
            first = cleaned.split(None, 1)[0].upper() if cleaned else ""
            if first in {"BEGIN", "COMMIT", "ROLLBACK", "END", "SAVEPOINT", "RELEASE", "VACUUM", "PRAGMA"}:
                raise UnsupportedError("Use the library transaction/configuration interfaces")
            rows, _ = self._db._backend.execute(statement, params, raw=True)
            return rows


class Transaction(Scope):
    def __init__(self, db):
        self._db = db
        self._live = True
        self._failed = False

    def transaction(self):
        self._failed = True
        raise TransactionError("Nested transactions are not supported")

    @contextmanager
    def _operation(self, write=False):
        try:
            self._db._assert_thread()
            if not self._live or self._db._active is not self:
                raise OwnershipError("Transaction handle has expired")
            if self._failed:
                raise TransactionError("Transaction has failed and must roll back")
            yield
        except BaseException:
            self._failed = True
            raise


class Database(Scope):
    def __init__(self, target, **options):
        self._backend = Backend(target, **options)
        self._db = self
        self._owner = str(uuid.uuid4())
        self._thread = threading.get_ident()
        self._active = None
        self._closed = False
        try:
            self._verify_metadata()
        except BaseException:
            self.close()
            raise

    def _assert_thread(self):
        if self._closed or threading.get_ident() != self._thread:
            raise OwnershipError("Database is closed or used from another thread")

    def _available(self):
        self._assert_thread()
        if self._active is not None:
            self._active._failed = True
            raise OwnershipError("Use the transaction-owned handle inside a transaction")

    @contextmanager
    def transaction(self, *, write=True):
        self._available()
        tx = Transaction(self)
        self._backend.begin(write)
        self._active = tx
        try:
            yield tx
            if tx._failed:
                raise TransactionError("A failed operation requires rollback")
            self._backend.commit()
        except BaseException:
            self._backend.rollback()
            raise
        finally:
            tx._live = False
            self._active = None

    @contextmanager
    def _operation(self, write=False):
        with self.transaction(write=write):
            yield

    def _verify_metadata(self):
        be = self._backend
        names = set(be.tables())
        private = {META, MIGRATIONS, VERSION}
        if names & private:
            if not private <= names:
                raise MigrationError("Incomplete melddb metadata")
            rows = be.execute(f"SELECT version FROM {VERSION}")[0]
            if rows != [{"version": FORMAT_VERSION}]:
                raise MigrationError("Unsupported melddb storage version")

    def _ensure_metadata(self):
        be = self._backend
        if be.exists(META):
            self._verify_metadata()
            return
        be.execute(f"CREATE TABLE {VERSION}(version INTEGER PRIMARY KEY)")
        be.execute(f"INSERT INTO {VERSION} VALUES (?)", (FORMAT_VERSION,))
        be.execute(f"CREATE TABLE {META}(name TEXT PRIMARY KEY, physical TEXT UNIQUE NOT NULL, "
                   "spec TEXT NOT NULL)")
        be.execute(f"CREATE TABLE {MIGRATIONS}(id TEXT PRIMARY KEY, checksum TEXT NOT NULL, "
                   "operations TEXT NOT NULL)")

    def _spec(self, name, kind=None):
        be = self._backend
        if not be.exists(META):
            raise NotFoundError(f"No managed object {name!r}")
        rows = be.execute(f"SELECT spec FROM {META} WHERE name=?", (name,))[0]
        if not rows:
            raise NotFoundError(f"No managed object {name!r}")
        spec = json.loads(rows[0]["spec"])
        if kind and spec["op"] != kind:
            raise ValidationError(f"{name!r} is not a {kind}")
        return spec

    def _register(self, spec):
        self._backend.execute(f"INSERT INTO {META} VALUES (?,?,?)",
                              (spec["name"], physical(spec["name"]), encode(spec)))

    def migrate(self, *migrations):
        from .migrations import apply
        with self._operation(write=True):
            apply(self, migrations)

    def inspect(self):
        with self._operation():
            return self._inspect()

    def _inspect(self):
        be = self._backend
        objects = []
        migrations = []
        if be.exists(META):
            for row in be.execute(f"SELECT * FROM {META} ORDER BY name")[0]:
                try:
                    spec = json.loads(row["spec"])
                except (ValueError, TypeError) as exc:
                    raise MigrationError("Invalid managed schema JSON") from exc
                objects.append({"name": row["name"], "physical": row["physical"],
                                "schema": spec})
            collation = 'COLLATE "C"' if be.pg else 'COLLATE BINARY'
            migrations = be.execute(f"SELECT * FROM {MIGRATIONS} ORDER BY id {collation}")[0]
        owned = {obj["physical"] for obj in objects} | {META, MIGRATIONS, VERSION}
        return {"format": FORMAT_VERSION, "backend": "postgresql" if be.pg else "sqlite",
                "experimental": be.pg, "objects": objects, "migrations": migrations,
                "external_tables": sorted(set(be.tables()) - owned)}

    def check(self):
        with self._operation():
            return self._check()

    def _check(self):
        from .inspection import structural_errors
        self._verify_metadata()
        be = self._backend
        if be.pg:
            errors = []
        else:
            errors = []
            for statement in ("PRAGMA integrity_check", "PRAGMA foreign_key_check"):
                try:
                    errors += [r for r in be.execute(statement)[0] if list(r.values()) != ["ok"]]
                except MeldDBError as exc:
                    errors.append({"code": "integrity_error", "check": statement, "message": str(exc)})
        errors += structural_errors(self)
        return {"ok": not errors, "errors": errors}

    def sqlite_runtime(self):
        self._available()
        return self._backend.sqlite_runtime()

    def maintain_sqlite(self, *, statistics="optimize", checkpoint="passive"):
        self._available()
        if self._backend.pg:
            raise UnsupportedError("SQLite maintenance is unavailable on PostgreSQL")
        if not self._backend.file_backed:
            raise UnsupportedError("SQLite maintenance requires a file-backed database")
        if self._backend.readonly:
            raise UnsupportedError("SQLite maintenance requires a writable database")
        if statistics not in (None, "optimize", "analyze"):
            raise ValidationError("statistics must be None, 'optimize', or 'analyze'")
        if checkpoint not in (None, "passive", "full", "restart", "truncate"):
            raise ValidationError(
                "checkpoint must be None, 'passive', 'full', 'restart', or 'truncate'"
            )
        if statistics is None and checkpoint is None:
            raise ValidationError("SQLite maintenance requires at least one action")
        return self._backend.maintain_sqlite(statistics=statistics, checkpoint=checkpoint)

    def backup(self, destination):
        from .transfer import backup
        self._available()
        return backup(self, destination)

    def export(self, destination):
        from .transfer import export
        with self._operation():
            return export(self, destination)

    def import_into(self, source):
        from .transfer import import_into
        with self._operation(write=True):
            return import_into(self, source)

    def close(self):
        if not self._closed:
            self._available()
            self._backend.conn.close()
            self._closed = True

    def __enter__(self):
        self._available()
        return self

    def __exit__(self, *args):
        self.close()
