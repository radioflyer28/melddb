"""Generate the shared logical fixture and restore it into fresh SQLite storage."""
import argparse
import tempfile
from pathlib import Path

import melddb
from melddb import Migration
from melddb import schema as s


def run(output=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifact = Path(output) if output else root / "export.json"
        with melddb.open(root / "source.db") as db:
            db.migrate(Migration("001", (s.collection("documents"),
                s.table("measurements", {"n": "integer", "blob": "bytes", "value": "float"}),
                s.relationship("contains", "documents", "measurements"))))
            with db.transaction() as tx:
                doc = tx.collection("documents").insert({"float": 1.0, "tiny": 1e-100,
                    "😀": "é", "\ue000": "Unicode order", "__proto__": {"safe": True}}, id="document")
                for name, number, data in [("minimum", -(2**63), b""), ("maximum", 2**63-1, b"\x00\xff")]:
                    row = tx.table("measurements").insert({"n": number, "blob": data, "value": 1.0}, id=name)
                    tx.relationship("contains").connect(tx.collection("documents").ref(doc),
                                                         tx.table("measurements").ref(row))
            db.sql("CREATE TABLE external_log(message TEXT)")
            mapping = next(o["physical"] for o in db.inspect()["objects"] if o["name"] == "documents")
            db.sql(f'UPDATE "{mapping}" SET version=?', (2**63-1,))
            db.export(artifact)
        with melddb.open(root / "restored.db") as restored:
            restored.import_into(artifact)
            assert restored.check()["ok"]
            assert restored.collection("documents").get("document")["version"] == 2**63-1
            assert restored.table("measurements").get("maximum")["n"] == 2**63-1
            assert restored.table("measurements").get("minimum")["blob"] == b""
            assert not restored.inspect()["external_tables"]
        with melddb.open(root / "restored.db", readonly=True) as reopened:
            assert reopened.check()["ok"]
    print("Logical transfer, exact int64, binary values, versions and exclusions: passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path)
    run(parser.parse_args().export)
