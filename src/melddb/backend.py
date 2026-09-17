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


def wal_safe(version=None):
    version = sqlite3.sqlite_version_info if version is None else version
    return (version >= (3, 51, 3) or
            (3, 50, 7) <= version < (3, 51, 0) or
            (3, 44, 6) <= version < (3, 45, 0))


def wal_unsupported():
    return UnsupportedError(
        "WAL requires SQLite with the WAL-reset fix (3.51.3+, 3.50.7+, "
        "or 3.44.6+ on those release branches); upgrade SQLite or explicitly "
        "select journal_mode='delete'"
    )


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
    def __init__(self, target, *, postgres=False, timeout=5, readonly=False,
                 journal_mode=None):
        self.pg = postgres
        self.readonly = readonly
        self.path = str(target)
        self.file_backed = not postgres and self.path != ":memory:"
        self.conn = None
        psycopg = None
        try:
            if postgres:
                if journal_mode is not None:
                    raise UnsupportedError("journal_mode is only available for SQLite")
                try:
                    import psycopg
                except ImportError as exc:
                    raise UnsupportedError("Install melddb[postgres]") from exc
                self.conn = psycopg.connect(target, autocommit=True)
                self.conn.execute("SELECT set_config('lock_timeout',%s,false)", (f"{int(timeout * 1000)}ms",))
                import json

                from psycopg.types.json import set_json_loads

                from .values import portable_json_integer
                set_json_loads(lambda data: json.loads(data, parse_int=portable_json_integer), self.conn)
            else:
                if journal_mode not in (None, "wal", "delete"):
                    raise ValidationError("journal_mode must be None, 'wal', or 'delete'")
                if not self.file_backed and journal_mode is not None:
                    raise UnsupportedError("journal_mode selection requires file-backed SQLite")
                if sqlite3.sqlite_version_info < (3, 38):
                    raise UnsupportedError("SQLite 3.38+ is required")
                existed = self.file_backed and Path(target).exists()
                selected = journal_mode
                if self.file_backed and not existed and selected is None:
                    selected = "wal" if wal_safe() else "delete"
                if selected == "wal" and not readonly and not wal_safe():
                    raise wal_unsupported()
                uri = Path(target).resolve().as_uri() + "?mode=ro" if readonly else str(target)
                self.conn = sqlite3.connect(uri, timeout=timeout, autocommit=True,
                                            uri=readonly)
                import json
                # Version alone does not establish JSON path correctness. Some
                # older distributions silently miss quoted keys, including in
                # constraint triggers; reject them before changing configuration.
                probe = json.dumps({'a"b': 1})
                path = '$.' + json.dumps('a"b')
                if self.conn.execute("SELECT json_extract(?,?)", (probe, path)).fetchone() != (1,):
                    raise UnsupportedError(
                        f"SQLite {sqlite3.sqlite_version} lacks required escaped JSON-key support; "
                        "use a Python build with a newer SQLite library (3.49.1 is verified)")
                if self.file_backed:
                    current = self.conn.execute("PRAGMA journal_mode").fetchone()[0]
                    if selected is not None and current != selected:
                        if readonly:
                            raise UnsupportedError(
                                f"read-only database uses journal_mode={current!r}, "
                                f"not requested {selected!r}"
                            )
                        current = self.conn.execute(
                            f"PRAGMA journal_mode={selected.upper()}"
                        ).fetchone()[0]
                    if selected is not None and current != selected:
                        raise UnsupportedError(
                            f"SQLite could not enable journal_mode={selected!r}; "
                            f"effective mode is {current!r}"
                        )
                    if current == "wal" and not readonly and not wal_safe():
                        raise wal_unsupported()
                self.conn.execute("PRAGMA foreign_keys=ON")
                self.conn.execute("PRAGMA synchronous=FULL")
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
                if isinstance(exc, sqlite3.Error):
                    code = getattr(exc, "sqlite_errorcode", 0)
                    kind = BusyError if code & 255 in (5, 6) else ConnectionError
                else:
                    kind = ConnectionError
                raise kind(str(exc)) from exc
            raise

    def sqlite_runtime(self):
        if self.pg:
            raise UnsupportedError("SQLite runtime information is unavailable on PostgreSQL")
        journal_mode = self.conn.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = self.conn.execute("PRAGMA synchronous").fetchone()[0]
        foreign_keys = self.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        qualified = wal_safe()
        if not self.file_backed:
            wal_reason = "not_file_backed"
        elif self.readonly:
            wal_reason = "read_only"
        elif qualified:
            wal_reason = "qualified"
        else:
            wal_reason = "wal_reset_fix_required"
        maintenance = self.file_backed and not self.readonly
        maintenance_reason = "available" if maintenance else (
            "not_file_backed" if not self.file_backed else "read_only"
        )
        return {
            "backend": "sqlite",
            "sqlite_version": sqlite3.sqlite_version,
            "file_backed": self.file_backed,
            "readonly": self.readonly,
            "journal_mode": journal_mode,
            "synchronous": synchronous,
            "foreign_keys": foreign_keys,
            "capabilities": {
                "wal": {"available": self.file_backed and not self.readonly and qualified,
                        "reason": wal_reason},
                "statistics": {"available": maintenance, "reason": maintenance_reason},
                "checkpoint": {"available": maintenance, "reason": maintenance_reason},
            },
        }

    def maintain_sqlite(self, *, statistics, checkpoint):
        result = {"statistics": None, "checkpoint": None}
        try:
            if statistics == "optimize":
                previous_limit = None
                if sqlite3.sqlite_version_info < (3, 46):
                    previous_limit = self.conn.execute("PRAGMA analysis_limit").fetchone()[0]
                    self.conn.execute("PRAGMA analysis_limit=400")
                try:
                    self.conn.execute("PRAGMA optimize=0x10002").fetchall()
                finally:
                    if previous_limit is not None:
                        self.conn.execute(f"PRAGMA analysis_limit={previous_limit}")
                result["statistics"] = {"action": "optimize", "completed": True}
            elif statistics == "analyze":
                self.conn.execute("ANALYZE").fetchall()
                result["statistics"] = {"action": "analyze", "completed": True}
            if checkpoint is not None:
                busy, log_frames, checkpointed = self.conn.execute(
                    f"PRAGMA wal_checkpoint({checkpoint.upper()})"
                ).fetchone()
                active = log_frames >= 0 and checkpointed >= 0
                result["checkpoint"] = {
                    "mode": checkpoint,
                    "busy": bool(busy),
                    "log_frames": log_frames if active else None,
                    "checkpointed_frames": checkpointed if active else None,
                    "complete": active and not busy and log_frames == checkpointed,
                    "wal_active": active,
                }
            return result
        except sqlite3.Error as exc:
            code = getattr(exc, "sqlite_errorcode", 0)
            kind = BusyError if code & 255 in (5, 6) else ValidationError
            raise kind(str(exc)) from exc

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
