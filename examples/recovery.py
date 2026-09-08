"""Back up live SQLite storage, reopen a fresh destination, and verify it."""
import tempfile
from pathlib import Path

import melddb


def run():
    with tempfile.TemporaryDirectory() as directory:
        source, destination = Path(directory) / "source.db", Path(directory) / "restored.db"
        with melddb.open(source) as db:
            db.collection("settings").insert({"theme": "dark"}, id="preferences")
            db.backup(destination)
        with melddb.open(destination) as restored:
            assert restored.check()["ok"]
            assert restored.collection("settings").get("preferences")["body"] == {"theme": "dark"}
            assert restored.inspect()["objects"][0]["name"] == "settings"
    print("Validated backup and independent restoration: passed")


if __name__ == "__main__":
    run()
