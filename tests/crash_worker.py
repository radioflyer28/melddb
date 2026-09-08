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
elif action == "evolution":
    checkpoint = args[0]
    execute = db._backend.execute
    def interrupted_evolution(sql, params=(), **kwargs):
        result = execute(sql, params, **kwargs)
        reached = ((checkpoint == "trigger" and sql.startswith("CREATE TRIGGER")) or
                   (checkpoint == "index" and sql.startswith("CREATE UNIQUE INDEX")) or
                   (checkpoint == "metadata" and sql.startswith("UPDATE _melddb_objects")) or
                   (checkpoint == "revision" and sql.startswith("INSERT INTO _melddb_migrations")) or
                   (checkpoint == "commit" and sql == "COMMIT"))
        if reached:
            os._exit(73)
        return result
    db._backend.execute = interrupted_evolution
    db.migrate(Migration("002", (s.require("docs", "key"), s.type_of("docs", "key", type="string"),
                                 s.index("docs", "key", unique=True))))
elif action in ("backup-before-publish", "backup-after-publish"):
    from melddb import transfer
    original_publish = transfer.publish
    def interrupted_publish(temp, destination):
        if action == "backup-before-publish":
            os._exit(73)
        original_publish(temp, destination)
        os._exit(73)
    transfer.publish = interrupted_publish
    db.backup(args[0])
elif action in ("import-before-commit", "import-after-commit"):
    execute = db._backend.execute
    def interrupted_import(sql, params=(), **kwargs):
        result = execute(sql, params, **kwargs)
        if ((action == "import-before-commit" and sql.startswith("INSERT INTO _melddb_migrations")) or
                (action == "import-after-commit" and sql == "COMMIT")):
            os._exit(73)
        return result
    db._backend.execute = interrupted_import
    db.import_into(args[0])
