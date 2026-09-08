"""Two concrete drivers. Internal SQL uses qmarks; raw SQL stays native."""
import sqlite3
from contextlib import suppress
from pathlib import Path

from .errors import (
    AlreadyExistsError,
    BusyError,
    ConnectionError,
    ConstraintError,
    UnsupportedError,
    ValidationError,
)


def quote(name):
    from .values import text
    return '"' + text(name).replace('"', '""') + '"'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def pg_sql(sql):
    # Generated SQL can contain quoted user keys/names, including ? and %.
    result, quoted, i = [], None, 0
    while i < len(sql):
        char = sql[i]
        if char == "%":
            result.append("%%")
        elif quoted:
            result.append(char)
            if char == quoted:
                if i + 1 < len(sql) and sql[i + 1] == quoted:
                    result.append(char)
                    i += 1
                else:
                    quoted = None
        elif char in ("'", '"'):
            quoted = char
            result.append(char)
        else:
            result.append("%s" if char == "?" else char)
        i += 1
    return "".join(result)


class Backend:
    def __init__(self, target, *, postgres=False, timeout=5, readonly=False):
        self.pg = postgres
        self.readonly = readonly
        self.path = str(target)
        self.conn = None
        psycopg = None
        try:
            if postgres:
                try:
                    import psycopg
                except ImportError as exc:
                    raise UnsupportedError("Install melddb[postgres]") from exc
                self.conn = psycopg.connect(target, autocommit=True)
                self.conn.execute("SELECT set_config('lock_timeout',%s,false)", (f"{int(timeout * 1000)}ms",))
            else:
                if sqlite3.sqlite_version_info < (3, 38):
                    raise UnsupportedError("SQLite 3.38+ is required")
                existed = target != ":memory:" and Path(target).exists()
                uri = Path(target).resolve().as_uri() + "?mode=ro" if readonly else str(target)
                self.conn = sqlite3.connect(uri, timeout=timeout, autocommit=True,
                                            uri=readonly)
                self.conn.execute("PRAGMA foreign_keys=ON")
                self.conn.execute("PRAGMA synchronous=FULL")
                if not existed and not readonly:
                    self.conn.execute("PRAGMA journal_mode=WAL")
                if self.conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise UnsupportedError("Foreign keys could not be enabled")
                self.conn.execute("SELECT json_valid('{}')").fetchone()
        except BaseException as exc:
            if self.conn is not None:
                with suppress(Exception):
                    self.conn.close()
            driver_error = isinstance(exc, (sqlite3.Error, OSError)) or (
                psycopg is not None and isinstance(exc, psycopg.Error)
            )
            if driver_error:
                raise ConnectionError(str(exc)) from exc
            raise

    def execute(self, sql, params=(), *, raw=False):
        try:
            if self.pg:
                statement = sql if raw else pg_sql(sql)
                cur = self.conn.execute(statement, params, prepare=True)
            else:
                cur = self.conn.execute(sql, params)
            names = [c[0] for c in cur.description] if cur.description else []
            rows = [dict(zip(names, row)) for row in cur.fetchall()] if names else []
            count = cur.rowcount
            cur.close()
            return rows, count
        except Exception as exc:
            if self.pg:
                import psycopg
                if not isinstance(exc, psycopg.Error):
                    raise
                code = exc.sqlstate or ""
                kind = (AlreadyExistsError if code == "23505" else
                        ConstraintError if code.startswith("23") else
                        BusyError if code in ("55P03", "40001", "40P01") else
                        ConnectionError if code.startswith("08") else ValidationError)
            else:
                if not isinstance(exc, sqlite3.Error):
                    raise
                code = getattr(exc, "sqlite_errorcode", 0)
                kind = (AlreadyExistsError if code in (1555, 2067) else
                        ConstraintError if isinstance(exc, sqlite3.IntegrityError) else
                        BusyError if code & 255 in (5, 6) else ValidationError)
            raise kind(str(exc)) from exc

    def begin(self, write=True):
        statement = ("BEGIN" if write else "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY") if self.pg else (
            "BEGIN IMMEDIATE" if write and not self.readonly else "BEGIN")
        self.execute(statement)

    def commit(self):
        self.execute("COMMIT")

    def rollback(self):
        self.execute("ROLLBACK")

    def exists(self, table):
        if self.pg:
            rows, _ = self.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() "
                "AND table_name=?", (table,))
        else:
            rows, _ = self.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                   (table,))
        return bool(rows)

    def tables(self):
        sql = ("SELECT table_name AS name FROM information_schema.tables "
               "WHERE table_schema=current_schema() AND table_type='BASE TABLE'" if self.pg else
               "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        return [row["name"] for row in self.execute(sql)[0]]
