"""Run identical settings/mixed correctness scenarios through three implementations."""
import json
import sqlite3
import tempfile
import time
from pathlib import Path

import melddb
from melddb import Migration
from melddb import schema as s


class Library:
    def __init__(self, path):
        self.db = melddb.open(path)
        self.db.migrate(Migration("001", (s.collection("docs"), s.table("activity", {"message": "text"}),
                                         s.relationship("links", "docs", "docs"))))

    def settings(self):
        c = self.db.collection("settings")
        return c.get(c.insert({"theme": "dark"})["id"])["body"]

    def mixed(self, fail):
        with self.db.transaction() as tx:
            c = tx.collection("docs")
            a, b = c.insert({"name": "a"}), c.insert({"name": "b"})
            tx.relationship("links").connect(c.ref(a), c.ref(b))
            tx.table("activity").insert({"message": "created"})
            if fail:
                raise RuntimeError("injected")

    def counts(self):
        description = {o["name"]: o["physical"] for o in self.db.inspect()["objects"]}
        return [self.db.sql(f'SELECT COUNT(*) AS n FROM "{description[name]}"')[0]["n"]
                for name in ("docs", "links", "activity")]

    def close(self):
        self.db.close()


class Driver:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE settings(id INTEGER PRIMARY KEY, body TEXT NOT NULL CHECK(json_valid(body)));
            CREATE TABLE docs(id INTEGER PRIMARY KEY, body TEXT NOT NULL CHECK(json_valid(body)));
            CREATE TABLE links(source INTEGER REFERENCES docs(id),target INTEGER REFERENCES docs(id),
                               PRIMARY KEY(source,target));
            CREATE TABLE activity(id INTEGER PRIMARY KEY,message TEXT);
        """)

    def settings(self):
        with self.db:
            ident = self.db.execute("INSERT INTO settings(body) VALUES (?)", (json.dumps({"theme": "dark"}),)).lastrowid
        return json.loads(self.db.execute("SELECT body FROM settings WHERE id=?", (ident,)).fetchone()[0])

    def mixed(self, fail):
        with self.db:
            a = self.db.execute("INSERT INTO docs(body) VALUES (?)", (json.dumps({"name": "a"}),)).lastrowid
            b = self.db.execute("INSERT INTO docs(body) VALUES (?)", (json.dumps({"name": "b"}),)).lastrowid
            self.db.execute("INSERT INTO links VALUES (?,?)", (a, b))
            self.db.execute("INSERT INTO activity(message) VALUES (?)", ("created",))
            if fail:
                raise RuntimeError("injected")

    def counts(self):
        return [self.db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ("docs", "links", "activity")]

    def close(self):
        self.db.close()


class Toolkit:
    def __init__(self, path):
        import sqlalchemy as sa
        self.sa = sa
        self.engine = sa.create_engine("sqlite:///" + str(path))
        @sa.event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        meta = sa.MetaData()
        self.settings_table = sa.Table("settings", meta, sa.Column("id", sa.Integer, primary_key=True),
                                       sa.Column("body", sa.JSON, nullable=False))
        self.docs = sa.Table("docs", meta, sa.Column("id", sa.Integer, primary_key=True),
                             sa.Column("body", sa.JSON, nullable=False))
        self.links = sa.Table("links", meta,
                              sa.Column("source", sa.ForeignKey("docs.id"), primary_key=True),
                              sa.Column("target", sa.ForeignKey("docs.id"), primary_key=True))
        self.activity = sa.Table("activity", meta, sa.Column("id", sa.Integer, primary_key=True),
                                 sa.Column("message", sa.Text))
        meta.create_all(self.engine)

    def settings(self):
        with self.engine.begin() as conn:
            result = conn.execute(self.settings_table.insert().values(body={"theme": "dark"}))
            return conn.execute(self.sa.select(self.settings_table.c.body).where(
                self.settings_table.c.id == result.inserted_primary_key[0])).scalar_one()

    def mixed(self, fail):
        with self.engine.begin() as conn:
            a = conn.execute(self.docs.insert().values(body={"name": "a"})).inserted_primary_key[0]
            b = conn.execute(self.docs.insert().values(body={"name": "b"})).inserted_primary_key[0]
            conn.execute(self.links.insert().values(source=a, target=b))
            conn.execute(self.activity.insert().values(message="created"))
            if fail:
                raise RuntimeError("injected")

    def counts(self):
        with self.engine.connect() as conn:
            return [conn.execute(self.sa.select(self.sa.func.count()).select_from(table)).scalar_one()
                    for table in (self.docs, self.links, self.activity)]

    def close(self):
        self.engine.dispose()


def run():
    results = {}
    for implementation in (Library, Driver, Toolkit):
        with tempfile.TemporaryDirectory() as directory:
            started = time.perf_counter()
            obj = implementation(Path(directory) / "test.db")
            try:
                assert obj.settings() == {"theme": "dark"}
                try:
                    obj.mixed(True)
                except RuntimeError:
                    pass
                assert obj.counts() == [0, 0, 0]
                obj.mixed(False)
                assert obj.counts() == [2, 1, 1]
                results[implementation.__name__] = {"settings": "pass", "rollback": "pass",
                                                   "mixed": "pass", "seconds_including_setup": time.perf_counter()-started}
            finally:
                obj.close()
    return results


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
