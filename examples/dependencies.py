"""Declared package dependencies with properties, BFS depths, and cascade deletion."""
import melddb
from melddb import Migration
from melddb import schema as s


def run():
    with melddb.open(":memory:") as db:
        db.migrate(Migration("001", (s.collection("packages"),
                                     s.relationship("depends_on", "packages", "packages", on_delete="cascade"))))
        with db.transaction() as tx:
            packages = tx.collection("packages")
            refs = {name: packages.ref(packages.insert({"name": name}, id=name))
                    for name in ("app", "parser", "syntax")}
            relation = tx.relationship("depends_on")
            relation.connect(refs["app"], refs["parser"], {"required": True})
            relation.connect(refs["parser"], refs["syntax"])
            relation.connect(refs["syntax"], refs["parser"])
        dependencies = db.relationship("depends_on")
        assert [(r["ref"].id, r["depth"]) for r in dependencies.neighbors(refs["app"], depth=4)] == [
            ("parser", 1), ("syntax", 2),
        ]
        assert [r["ref"].id for r in dependencies.neighbors(refs["parser"], direction="in")] == ["app", "syntax"]
        dependencies.replace_properties(refs["app"], refs["parser"], {"required": False})
        db.collection("packages").delete("parser")
        assert dependencies.edges(refs["app"]) == []
    print("Dependencies, reverse traversal, cycles, properties and cascade deletion: passed")


if __name__ == "__main__":
    run()
