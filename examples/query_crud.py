"""Document queries and a managed address book alongside an existing SQL table."""
import argparse
import sqlite3
from pathlib import Path

import melddb
from melddb import Migration, field
from melddb import schema as s
from melddb.errors import ConflictError


def run(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "queries.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy_notes(note TEXT)")
        connection.execute("INSERT INTO legacy_notes VALUES (?)", ("existing data",))

    with melddb.open(path) as db:
        docs = db.collection("packages")
        first = docs.insert({"name": "editor", "downloads": 50, "license": None})
        docs.insert({"name": "parser", "downloads": 100})
        selected = docs.find(field("downloads").gte(50) & ~field("license").is_null(),
                             order_by=field("downloads"), descending=True, limit=10)
        assert [row["body"]["name"] for row in selected] == ["parser"]
        docs.replace(first["id"], {"name": "editor", "downloads": 75}, expected_version=1)
        try:
            docs.delete(first["id"], expected_version=1)
        except ConflictError:
            pass
        else:
            raise AssertionError("A stale document version must conflict")

        db.migrate(Migration("001", (s.table("contacts", {
            "name": "text", "email": "text", "favorite": "boolean",
        }),)))
        contacts = db.table("contacts")
        ada = contacts.insert({"name": "Ada", "email": "ada@example.test", "favorite": False})
        contacts.update(ada["id"], {"favorite": True})
        assert contacts.find(field("favorite").eq(True), columns=["email"]) == [
            {"email": "ada@example.test"},
        ]
        assert db.sql("WITH notes AS (SELECT note FROM legacy_notes) SELECT note FROM notes") == [
            {"note": "existing data"},
        ]
        assert contacts.delete(ada["id"])
        assert contacts.get(ada["id"]) is None

    with melddb.open(path) as reopened:
        assert reopened.collection("packages").get(first["id"])["version"] == 2
    print("Document queries, conditional writes, address book and existing SQL: passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="New disposable output directory")
    run(parser.parse_args().directory)
