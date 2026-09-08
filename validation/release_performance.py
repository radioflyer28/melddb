"""Local measurements for document indexes, activity batching and UUID locality."""
import argparse
import json
import platform
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

import melddb
from melddb import Migration, field
from melddb import schema as s
from melddb.identifiers import new_id


def measure(directory):
    count = 10000
    timings = {}
    with melddb.open(directory / "managed.db") as db:
        db.migrate(Migration("001", (s.collection("docs"), s.index("docs", "n"),
                                     s.table("activity", {"n": "integer", "message": "text"}))))
        started = time.perf_counter()
        with db.transaction() as tx:
            for n in range(count):
                tx.collection("docs").insert({"n": n})
        timings["managed_document_insert"] = time.perf_counter() - started
        started = time.perf_counter()
        for n in range(0, count, 100):
            assert db.collection("docs").find(field("n").eq(n))[0]["body"] == {"n": n}
        timings["managed_100_indexed_lookups"] = time.perf_counter() - started
        started = time.perf_counter()
        with db.transaction() as tx:
            for n in range(count):
                tx.table("activity").insert({"n": n, "message": "event"})
        timings["managed_activity_batch"] = time.perf_counter() - started
        assert db.check()["ok"]
    with closing(sqlite3.connect(directory / "driver.db", autocommit=True)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE docs(id TEXT PRIMARY KEY,body TEXT)")
        connection.execute("CREATE INDEX lookup ON docs(json_extract(body,'$.n'))")
        connection.execute("CREATE TABLE activity(id TEXT PRIMARY KEY,n INTEGER,message TEXT)")
        started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany("INSERT INTO docs VALUES (?,?)", ((new_id(), json.dumps({"n": n})) for n in range(count)))
        connection.execute("COMMIT")
        timings["driver_document_insert"] = time.perf_counter() - started
        started = time.perf_counter()
        for n in range(0, count, 100):
            assert json.loads(connection.execute("SELECT body FROM docs WHERE json_extract(body,'$.n')=?", (n,)).fetchone()[0]) == {"n": n}
        timings["driver_100_indexed_lookups"] = time.perf_counter() - started
        started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany("INSERT INTO activity VALUES (?,?,?)", ((new_id(), n, "event") for n in range(count)))
        connection.execute("COMMIT")
        timings["driver_activity_batch"] = time.perf_counter() - started
    locality = {}
    for kind, generate in (("uuid4", lambda: str(uuid.uuid4())), ("uuid7", new_id)):
        ids = [generate() for _ in range(count)]
        with closing(sqlite3.connect(directory / f"{kind}.db", autocommit=True)) as connection:
            connection.execute("CREATE TABLE records(id TEXT PRIMARY KEY,body TEXT)")
            started = time.perf_counter()
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany("INSERT INTO records VALUES (?,'example')", ((i,) for i in ids))
            connection.execute("COMMIT")
            locality[kind] = {"seconds": time.perf_counter()-started,
                              "pages": connection.execute("PRAGMA page_count").fetchone()[0]}
    return {"environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                            "platform": platform.platform(), "processor": platform.processor()},
            "records_per_workload": count, "seconds": timings, "uuid_index_insertion": locality,
            "scope": "Single local sample. Managed checked per-record API versus simpler sqlite3 executemany; "
                     "one write transaction each. UUID insertion excludes generation. No universal latency claims."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        report = json.dumps(measure(Path(directory)), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
