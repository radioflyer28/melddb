"""Deliberately exits without cleanup; invoked only against disposable test databases."""
import os
import sys

import melddb
from melddb import Migration
from melddb import schema as s

path, action, *args = sys.argv[1:]
db = melddb.open(path, timeout=0.05)
if action in ("transaction-before", "transaction-after"):
    with db.transaction() as tx:
        tx.collection("docs").insert({"committed": True}, id="new")
        if action.endswith("before"):
            os._exit(73)
    os._exit(73)
elif action == "busy":
    try:
        db.collection("docs").insert({})
    except melddb.errors.BusyError:
        os._exit(74)
    os._exit(75)
elif action in ("migration", "import"):
    execute = db._backend.execute
    def interrupted(sql, params=(), **kwargs):
        result = execute(sql, params, **kwargs)
        if sql.startswith('INSERT INTO "ad_'):
            os._exit(73)
        if action == "migration" and sql.startswith('CREATE TABLE "ad_'):
            os._exit(73)
        return result
    db._backend.execute = interrupted
    if action == "migration":
        db.migrate(Migration("001", (s.collection("new"),)))
    else:
        db.import_into(args[0])
elif action == "backup":
    original = db._backend.conn
    class Interrupted:
        def backup(self, target):
            original.backup(target, pages=1, progress=lambda *_: os._exit(73))
    db._backend.conn = Interrupted()
    db.backup(args[0])
