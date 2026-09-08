"""Validate, explicitly repair, install constraints, then verify SQL enforcement."""
import melddb
from melddb import Migration
from melddb import schema as s
from melddb.errors import ConstraintError, ValidationError


def run():
    with melddb.open(":memory:") as db:
        docs = db.collection("contacts")
        docs.insert({"name": "Ada"}, id="ada")
        revision = Migration("001", (s.require("contacts", "email"),
                                     s.type_of("contacts", "email", type="string"),
                                     s.index("contacts", "email", unique=True)))
        try:
            db.migrate(revision)
        except ValidationError as error:
            assert error.violations[0]["id"] == "ada"
            assert db.inspect()["migrations"] == []
        else:
            raise AssertionError("Existing data should prevent the migration")
        # Data repair is an explicit application decision, never automatic coercion.
        docs.replace("ada", {"name": "Ada", "email": "ada@example.test"})
        db.migrate(revision)
        db.migrate(revision)  # Checksum-identical replay is harmless.
        physical = db.inspect()["objects"][0]["physical"]
        try:
            db.sql(f'UPDATE "{physical}" SET body=? WHERE id=?', ('{}', "ada"))
        except ConstraintError:
            pass
        else:
            raise AssertionError("SQL must preserve the installed constraint")
        assert docs.get("ada")["body"]["email"] == "ada@example.test"
        assert db.check()["ok"]
    print("Constraint validation, explicit repair, replay and SQL enforcement: passed")


if __name__ == "__main__":
    run()
