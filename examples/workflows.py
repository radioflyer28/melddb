"""Five small applications and the assembled recovery workflow; no GUI or framework."""
import argparse
from pathlib import Path

import melddb
from melddb import Migration, field
from melddb import schema as s


def run(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with melddb.open(directory / "application.db") as db:
        # 1. Settings: no classes, migrations, or session setup.
        settings = db.collection("settings")
        preference = settings.insert({"theme": "dark"})
        assert settings.get(preference["id"])["body"]["theme"] == "dark"
        db.migrate(Migration("001", (
            s.table("contacts", {"name": "text", "email": "text"}),
            s.collection("packages"),
            s.relationship("depends_on", "packages", "packages", on_delete="cascade"),
            s.table("activity", {"message": "text", "sequence": "integer"}),
        )))
        # 2. Relational address book.
        contact = db.table("contacts").insert({"name": "Ada", "email": "ada@example.test"})
        assert db.table("contacts").find(field("name").eq("Ada"), columns=["email"])
        db.table("contacts").update(contact["id"], {"name": "Ada L."})
        # 3. Persistent package dependencies, composed atomically with an activity row.
        with db.transaction() as tx:
            packages = tx.collection("packages")
            app = packages.insert({"name": "application", "version": 1})
            dep = packages.insert({"name": "dependency", "version": 1})
            tx.relationship("depends_on").connect(packages.ref(app), packages.ref(dep))
            tx.table("activity").insert({"message": "dependency added", "sequence": 0})
        packages = db.collection("packages")
        assert db.relationship("depends_on").neighbors(packages.ref(app))[0]["record"] == dep
        # 4. Batched structured logging and explicit retention.
        with db.transaction() as tx:
            for n in range(1, 11):
                tx.table("activity").insert({"message": f"step {n}", "sequence": n})
        physical = next(o["physical"] for o in db.inspect()["objects"] if o["name"] == "activity")
        db.sql(f'DELETE FROM "{physical}" WHERE sequence < ?', (5,))
        # 5. Existing SQL objects need no conversion.
        db.sql("CREATE TABLE IF NOT EXISTS external_metrics (value INTEGER)")
        db.sql("INSERT INTO external_metrics VALUES (?)", (42,))
        assert db.sql("WITH m AS (SELECT MAX(value) AS n FROM external_metrics) SELECT n FROM m") == [{"n": 42}]
        before = len(packages.find())
        try:
            with db.transaction() as tx:
                tx.collection("packages").insert({"name": "must roll back"})
                raise RuntimeError("simulate a failed operation")
        except RuntimeError:
            pass
        assert len(packages.find()) == before
        assert db.check()["ok"]
        db.backup(directory / "backup.db")
        db.export(directory / "export.json")
    with melddb.open(directory / "application.db") as reopened:
        assert reopened.collection("packages").get(app["id"])
    with melddb.open(directory / "restored.db") as restored:
        restored.import_into(directory / "export.json")
        assert restored.check()["ok"]
        assert restored.collection("packages").get(app["id"]) == app
    return directory / "export.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="New disposable output directory")
    print(run(parser.parse_args().directory))
