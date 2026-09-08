"""Executable Gate A comparison; all application helpers are included in metrics."""
import argparse
import ast
import inspect
import json
import platform
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy as sa

import melddb
from melddb import Migration
from melddb import schema as s


class InjectedFailure(RuntimeError):
    pass


class Aborted(RuntimeError):
    pass


def checkpoint(requested, completed):
    if requested == completed:
        raise InjectedFailure(f"after operation {completed}")


class Guard:
    """Baseline helper: caught SQL failures must still abort the enclosing scope."""

    def __init__(self, execute):
        self.execute = execute
        self.failed = False

    def __call__(self, *args, **kwargs):
        if self.failed:
            raise Aborted("Transaction already failed")
        try:
            return self.execute(*args, **kwargs)
        except Exception:
            self.failed = True
            raise

    def finish(self):
        if self.failed:
            raise Aborted("Caught failure requires rollback")


def configured_connection(path):
    existed = Path(path).exists()
    connection = sqlite3.connect(path, autocommit=True, timeout=5)
    connection.execute("PRAGMA foreign_keys=ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise RuntimeError("Foreign keys unavailable")
    connection.execute("PRAGMA synchronous=FULL")
    if not existed:
        connection.execute("PRAGMA journal_mode=WAL")
    return connection


def toolkit_engine(path):
    def create_connection():
        connection = configured_connection(path)
        connection.autocommit = sqlite3.LEGACY_TRANSACTION_CONTROL
        connection.isolation_level = None
        return connection

    engine = sa.create_engine(sa.URL.create("sqlite", database=str(path)),
                              creator=create_connection)

    @sa.event.listens_for(engine, "begin")
    def begin(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def library_settings(path):
    with melddb.open(path) as db:
        collection = db.collection("settings")
        record = collection.insert({"theme": "dark"})
        return collection.get(record["id"])["body"]


def driver_settings(path):
    connection = configured_connection(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY NOT NULL, body TEXT)")
        ident = str(uuid.uuid4())
        connection.execute("INSERT INTO settings VALUES (?,?)", (ident, json.dumps({"theme": "dark"})))
        result = json.loads(connection.execute("SELECT body FROM settings WHERE id=?", (ident,)).fetchone()[0])
        connection.execute("COMMIT")
        return result
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def toolkit_settings(path):
    engine = toolkit_engine(path)
    table = sa.Table("settings", sa.MetaData(),
                     sa.Column("id", sa.Text, primary_key=True), sa.Column("body", sa.JSON))
    try:
        with engine.begin() as connection:
            table.create(connection, checkfirst=True)
            ident = str(uuid.uuid4())
            connection.execute(table.insert().values(id=ident, body={"theme": "dark"}))
            return connection.execute(sa.select(table.c.body).where(table.c.id == ident)).scalar_one()
    finally:
        engine.dispose()


class Library:
    constraint_error = melddb.errors.ConstraintError
    aborted_error = melddb.errors.TransactionError

    def __init__(self, path):
        self.db = melddb.open(path)
        self.db.migrate(Migration("001", (
            s.collection("docs"), s.table("activity", {"message": "text"}),
            s.relationship("links", "docs", "docs"),
        )))

    def mixed(self, failure=None):
        with self.db.transaction() as tx:
            docs = tx.collection("docs")
            a = docs.insert({"name": "a"})
            checkpoint(failure, 1)
            b = docs.insert({"name": "b"})
            checkpoint(failure, 2)
            links = tx.relationship("links")
            links.connect(docs.ref(a), docs.ref(b))
            checkpoint(failure, 3)
            tx.table("activity").insert({"message": "created"})
            checkpoint(failure, 4)
            if failure in ("duplicate", "caught_duplicate"):
                try:
                    links.connect(docs.ref(a), docs.ref(b))
                except self.constraint_error:
                    if failure != "caught_duplicate":
                        raise
            elif failure == "missing":
                links.connect(docs.ref(a), docs.ref("missing"))
            elif failure == "restrict":
                docs.delete(a["id"])

    def snapshot(self):
        names = {o["name"]: o["physical"] for o in self.db.inspect()["objects"]}
        return {name: self.db.sql(f'SELECT * FROM "{names[name]}"') for name in names}

    def outside_query(self):
        name = next(o["physical"] for o in self.db.inspect()["objects"] if o["name"] == "docs")
        return self.db.sql(f'SELECT json_extract(body,\'$.name\') AS name, '
                           f'row_number() OVER (ORDER BY json_extract(body,\'$.name\')) AS rank FROM "{name}"')

    def close(self):
        self.db.close()


class Driver:
    constraint_error = sqlite3.IntegrityError
    aborted_error = Aborted

    def __init__(self, path):
        self.db = configured_connection(path)
        with self.transaction() as execute:
            execute("CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY NOT NULL, "
                    "body TEXT NOT NULL CHECK(json_valid(body) AND json_type(body)='object'))")
            execute("CREATE TABLE IF NOT EXISTS links(source_id TEXT NOT NULL REFERENCES docs(id) "
                    "ON DELETE RESTRICT,target_id TEXT NOT NULL REFERENCES docs(id) ON DELETE RESTRICT,"
                    "PRIMARY KEY(source_id,target_id))")
            execute("CREATE TABLE IF NOT EXISTS activity(id TEXT PRIMARY KEY NOT NULL,message TEXT)")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        guard = Guard(self.db.execute)
        try:
            yield guard
            guard.finish()
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def mixed(self, failure=None):
        with self.transaction() as execute:
            a, b = str(uuid.uuid4()), str(uuid.uuid4())
            execute("INSERT INTO docs VALUES (?,?)", (a, json.dumps({"name": "a"})))
            checkpoint(failure, 1)
            execute("INSERT INTO docs VALUES (?,?)", (b, json.dumps({"name": "b"})))
            checkpoint(failure, 2)
            execute("INSERT INTO links VALUES (?,?)", (a, b))
            checkpoint(failure, 3)
            execute("INSERT INTO activity VALUES (?,?)", (str(uuid.uuid4()), "created"))
            checkpoint(failure, 4)
            if failure in ("duplicate", "caught_duplicate"):
                try:
                    execute("INSERT INTO links VALUES (?,?)", (a, b))
                except self.constraint_error:
                    if failure != "caught_duplicate":
                        raise
            elif failure == "missing":
                execute("INSERT INTO links VALUES (?,?)", (a, "missing"))
            elif failure == "restrict":
                execute("DELETE FROM docs WHERE id=?", (a,))

    def snapshot(self):
        result = {}
        with self.transaction() as execute:
            for name in ("docs", "links", "activity"):
                cursor = execute(f'SELECT * FROM "{name}"')
                result[name] = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor]
        return result

    def outside_query(self):
        return [dict(zip(("name", "rank"), row)) for row in self.db.execute(
            "SELECT json_extract(body,'$.name'), row_number() OVER (ORDER BY json_extract(body,'$.name')) FROM docs"
        )]

    def close(self):
        self.db.close()


class Toolkit:
    constraint_error = sa.exc.IntegrityError
    aborted_error = Aborted

    def __init__(self, path):
        self.engine = toolkit_engine(path)
        meta = sa.MetaData()
        self.docs = sa.Table("docs", meta, sa.Column("id", sa.Text, primary_key=True),
                             sa.Column("body", sa.JSON, nullable=False),
                             sa.CheckConstraint("json_valid(body) AND json_type(body)='object'"))
        self.links = sa.Table("links", meta,
                              sa.Column("source_id", sa.ForeignKey("docs.id", ondelete="RESTRICT"), primary_key=True),
                              sa.Column("target_id", sa.ForeignKey("docs.id", ondelete="RESTRICT"), primary_key=True))
        self.activity = sa.Table("activity", meta, sa.Column("id", sa.Text, primary_key=True),
                                 sa.Column("message", sa.Text))
        meta.create_all(self.engine)

    def mixed(self, failure=None):
        with self.engine.begin() as connection:
            execute = Guard(connection.execute)
            a, b = str(uuid.uuid4()), str(uuid.uuid4())
            execute(self.docs.insert().values(id=a, body={"name": "a"}))
            checkpoint(failure, 1)
            execute(self.docs.insert().values(id=b, body={"name": "b"}))
            checkpoint(failure, 2)
            execute(self.links.insert().values(source_id=a, target_id=b))
            checkpoint(failure, 3)
            execute(self.activity.insert().values(id=str(uuid.uuid4()), message="created"))
            checkpoint(failure, 4)
            if failure in ("duplicate", "caught_duplicate"):
                try:
                    execute(self.links.insert().values(source_id=a, target_id=b))
                except self.constraint_error:
                    if failure != "caught_duplicate":
                        raise
            elif failure == "missing":
                execute(self.links.insert().values(source_id=a, target_id="missing"))
            elif failure == "restrict":
                execute(self.docs.delete().where(self.docs.c.id == a))
            execute.finish()

    def snapshot(self):
        with self.engine.connect() as connection:
            return {table.name: [dict(row) for row in connection.execute(sa.select(table)).mappings()]
                    for table in (self.docs, self.links, self.activity)}

    def outside_query(self):
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(sa.text(
                "SELECT json_extract(body,'$.name') AS name, "
                "row_number() OVER (ORDER BY json_extract(body,'$.name')) AS rank FROM docs"
            )).mappings()]

    def close(self):
        self.engine.dispose()


IMPLEMENTATIONS = (Library, Driver, Toolkit)
SETTINGS = {Library: library_settings, Driver: driver_settings, Toolkit: toolkit_settings}
HELPERS = {Library: (), Driver: (Guard, Aborted, configured_connection),
           Toolkit: (Guard, Aborted, configured_connection, toolkit_engine)}


def verify_snapshot(snapshot, batches):
    assert {k: len(v) for k, v in snapshot.items()} == {
        "docs": batches * 2, "links": batches, "activity": batches,
    }
    names = {}
    for row in snapshot["docs"]:
        uuid.UUID(row["id"])
        body = json.loads(row["body"]) if isinstance(row["body"], str) else row["body"]
        names[row["id"]] = body["name"]
    for edge in snapshot["links"]:
        assert (names[edge["source_id"]], names[edge["target_id"]]) == ("a", "b")
    assert all(row["message"] == "created" for row in snapshot["activity"])


def verify_case(implementation, directory, failure):
    path = directory / "mixed.db"
    obj = implementation(path)
    try:
        obj.mixed()
        before = obj.snapshot()
        verify_snapshot(before, 1)
        error_type = (InjectedFailure if isinstance(failure, int) else
                      implementation.aborted_error if failure == "caught_duplicate" else
                      implementation.constraint_error)
        try:
            obj.mixed(failure)
        except error_type:
            pass
        else:
            raise AssertionError(f"Expected {error_type.__name__} for {failure}")
        assert obj.snapshot() == before
        assert obj.outside_query() == [{"name": "a", "rank": 1}, {"name": "b", "rank": 2}]
    finally:
        obj.close()
    reopened = implementation(path)
    try:
        assert reopened.snapshot() == before
        reopened.mixed()
        verify_snapshot(reopened.snapshot(), 2)
    finally:
        reopened.close()


def metrics(*objects):
    sources = []
    for obj in objects:
        full_source = Path(inspect.getsourcefile(obj)).read_text(encoding="utf-8")
        node = next(node for node in ast.parse(full_source).body
                    if getattr(node, "name", None) == obj.__name__)
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        sources.append("\n".join(full_source.splitlines()[start-1:node.end_lineno]))
    source = "\n".join(sources)
    tree = ast.parse(source)
    return {
        "nonblank_lines": sum(bool(line.strip()) for line in source.splitlines()),
        "ast_statements": sum(isinstance(node, ast.stmt) for node in ast.walk(tree)),
    }


def run():
    results = {}
    cases = (1, 2, 3, 4, "duplicate", "missing", "restrict", "caught_duplicate")
    for implementation in IMPLEMENTATIONS:
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            assert SETTINGS[implementation](directory / "settings.db") == {"theme": "dark"}
            for index, failure in enumerate(cases):
                case_dir = directory / str(index)
                case_dir.mkdir()
                verify_case(implementation, case_dir, failure)
        results[implementation.__name__] = {
            "settings": "pass", "mixed_cases": {str(case): "pass" for case in cases},
            "metrics": {
                "adapter_including_fault_branches": metrics(implementation),
                "application_helpers": metrics(*HELPERS[implementation]),
                "settings_function": metrics(SETTINGS[implementation]),
                "total": metrics(implementation, SETTINGS[implementation], *HELPERS[implementation]),
            },
        }
    return {"environment": {"python": platform.python_version(), "platform": platform.platform(),
                             "sqlite": sqlite3.sqlite_version, "sqlalchemy": sa.__version__},
            "implementations": results,
            "measurement_scope": "Adapter + settings + all application helpers; imports and common test harness excluded. "
                                 "Fault-injection branches included. No latency comparison or full SDK equivalence claim."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run(), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
