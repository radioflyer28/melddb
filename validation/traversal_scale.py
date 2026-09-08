"""Reproducible 10,000-document/50,000-edge SQLite workload and driver baseline."""
import argparse
import json
import math
import platform
import sqlite3
import tempfile
import time
from pathlib import Path

import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import TraversalLimitError


def fixture():
    identifiers = [f"n{i:05}" for i in range(10000)]
    links = [(identifiers[0], ident) for ident in identifiers[1:]]
    for source in range(1, len(identifiers)):
        for step in range(5):
            links.append((identifiers[source], identifiers[(source + step) % len(identifiers)]))
            if len(links) == 50000:
                return identifiers, links
    raise AssertionError("Fixture did not reach 50,000 edges")


def driver_walk(connection, origin):
    seen, frontier, depths, queries = {origin}, [origin], {}, 0
    connection.execute("BEGIN")
    try:
        for depth in (1, 2):
            upcoming = []
            for offset in range(0, len(frontier), 400):
                batch = frontier[offset:offset+400]
                queries += 1
                for (target,) in connection.execute(
                    f"SELECT target_id FROM edges WHERE source_id IN ({','.join('?' for _ in batch)}) "
                    "ORDER BY source_id,target_id", batch,
                ):
                    if target not in seen:
                        seen.add(target)
                        depths[target] = depth
                        upcoming.append(target)
            frontier = upcoming
        records = {}
        identifiers = sorted(depths)
        for offset in range(0, len(identifiers), 400):
            batch = identifiers[offset:offset+400]
            queries += 1
            for ident, version, body in connection.execute(
                f"SELECT id,version,body FROM nodes WHERE id IN ({','.join('?' for _ in batch)})", batch,
            ):
                records[ident] = {"id": ident, "version": version, "body": json.loads(body)}
        connection.execute("COMMIT")
        return records, depths, queries
    except BaseException:
        connection.execute("ROLLBACK")
        raise


def run(directory):
    identifiers, links = fixture()
    with melddb.open(directory / "managed.db") as db:
        db.migrate(Migration("001", (s.collection("nodes"),
                                     s.relationship("edges", "nodes", "nodes", on_delete="cascade"))))
        started = time.perf_counter()
        with db.transaction() as tx:
            nodes, edges = tx.collection("nodes"), tx.relationship("edges")
            for i, ident in enumerate(identifiers):
                nodes.insert({"n": i}, id=ident)
            for source, target in links:
                edges.connect(nodes.ref(source), nodes.ref(target))
        managed_insert = time.perf_counter() - started
        original = db._backend.execute
        statements = []

        def counted(statement, *args, **kwargs):
            statements.append(statement)
            return original(statement, *args, **kwargs)

        db._backend.execute = counted
        started = time.perf_counter()
        result = db.relationship("edges").neighbors(db.collection("nodes").ref(identifiers[0]), depth=2)
        managed_walk = time.perf_counter() - started
        db._backend.execute = original
        batch_queries = sum(" IN (" in statement for statement in statements)
        assert batch_queries == 1 + 2 * math.ceil(9999/400)
        assert len(result) == 9999 and all(row["depth"] == 1 for row in result)
        try:
            db.relationship("edges").neighbors(db.collection("nodes").ref(identifiers[0]),
                                               depth=2, max_edges=49999)
        except TraversalLimitError:
            pass
        else:
            raise AssertionError("Traversal must report exceeding the edge budget")
        assert db.check()["ok"]

    connection = sqlite3.connect(directory / "driver.db", autocommit=True)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE nodes(id TEXT PRIMARY KEY NOT NULL,version INTEGER,body TEXT)")
        connection.execute("CREATE TABLE edges(source_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,"
                           "target_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,PRIMARY KEY(source_id,target_id))")
        connection.execute("CREATE INDEX incoming ON edges(target_id,source_id)")
        started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany("INSERT INTO nodes VALUES (?,1,?)",
                               ((ident, json.dumps({"n": i})) for i, ident in enumerate(identifiers)))
        connection.executemany("INSERT INTO edges VALUES (?,?)", links)
        connection.execute("COMMIT")
        driver_insert = time.perf_counter() - started
        started = time.perf_counter()
        records, depths, driver_queries = driver_walk(connection, identifiers[0])
        driver_time = time.perf_counter() - started
        assert records == {row["ref"].id: row["record"] for row in result}
        assert depths == {row["ref"].id: row["depth"] for row in result}
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()
    return {
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                        "platform": platform.platform(), "processor": platform.processor()},
        "fixture": {"documents": 10000, "edges": 50000, "depth": 2, "returned_records": 9999},
        "melddb": {"insert_seconds": managed_insert, "traversal_seconds": managed_walk,
                   "traversal_sql_statements": len(statements), "batched_selects": batch_queries},
        "driver": {"insert_seconds": driver_insert, "traversal_seconds": driver_time,
                   "batched_selects": driver_queries},
        "checks": {"same_records_and_depths": True, "edge_budget_overflow_raises": True,
                   "integrity": True},
        "scope": "Single local sample; data generation/schema setup excluded. MeldDB per-record API in one "
                 "transaction versus sqlite3 executemany. Driver has fewer checks. Both traversals batch 400 IDs "
                 "and fetch document bodies. Not a universal latency guarantee.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        report = json.dumps(run(Path(directory)), indent=2) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
