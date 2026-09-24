"""Local evidence for transaction-scoped bulk SQL; not a universal benchmark."""
import argparse
import json
import platform
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

import melddb


def _configure(connection):
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("CREATE TABLE events(sequence INTEGER PRIMARY KEY, value TEXT NOT NULL)")


def _melddb_workload(path, count, *, bulk):
    with melddb.open(path, journal_mode="delete") as db:
        db.sql("CREATE TABLE events(sequence INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        started = time.perf_counter()
        with db.transaction() as tx:
            if bulk:
                summary = tx.sql_many(
                    "INSERT INTO events VALUES (?,?)",
                    ((sequence, "event") for sequence in range(count)),
                )
                calls = 1
            else:
                for sequence in range(count):
                    tx.sql("INSERT INTO events VALUES (?,?)", (sequence, "event"))
                summary = {"parameter_sets": count, "affected_rows": count}
                calls = count
        seconds = time.perf_counter() - started
        rows = db.sql("SELECT COUNT(*) AS count FROM events", write=False)[0]["count"]
    assert rows == count
    assert summary == {"parameter_sets": count, "affected_rows": count}
    return {"seconds": seconds, "sql_calls": calls, "rows": rows, "summary": summary}


def _driver_workload(path, count):
    with closing(sqlite3.connect(path, autocommit=True)) as connection:
        _configure(connection)
        started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "INSERT INTO events VALUES (?,?)",
            ((sequence, "event") for sequence in range(count)),
        )
        connection.execute("COMMIT")
        seconds = time.perf_counter() - started
        rows = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert rows == count
    return {"seconds": seconds, "sql_calls": 1, "rows": rows}


def measure(directory, *, count=10000):
    directory = Path(directory)
    return {
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "records": count,
        "workloads": {
            "transaction_sql_row_by_row": _melddb_workload(
                directory / "row-by-row.db", count, bulk=False
            ),
            "transaction_sql_many": _melddb_workload(
                directory / "sql-many.db", count, bulk=True
            ),
            "sqlite3_executemany": _driver_workload(
                directory / "driver.db", count
            ),
        },
        "scope": (
            "Single local SQLite sample with one explicit write transaction per workload, "
            "identical rows, DELETE journal mode, FULL synchronous writes, and native parameter "
            "binding. Timings are local evidence only, not universal performance guarantees."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    with tempfile.TemporaryDirectory() as directory:
        report = json.dumps(measure(directory, count=args.count), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
