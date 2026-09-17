"""S10 adversarial artifacts, snapshot consistency and second-language proof."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from test_transfer import fixture

import melddb
from melddb.errors import AlreadyExistsError, MeldDBError
from melddb.transfer import canonical, checksum


def artifact(tmp_path):
    path = tmp_path / "export.json"
    with melddb.open(tmp_path / "source.db") as source:
        fixture(source)
        source.collection("docs").replace(
            "a", {"float": 1.0, "tiny": 1e-100, "😀": "é", "\ue000": "x"}
        )
        source.table("rows").insert({"blob": b"", "big": -(2**63)}, id="minimum")
        source.export(path)
    return path


@pytest.mark.parametrize(
    "damage",
    [
        "format_bool",
        "unknown",
        "objects",
        "schema",
        "rows",
        "version_bool",
        "version_overflow",
        "id",
        "body",
        "duplicate_id",
        "binary_extra",
        "binary_invalid",
        "binary_padbits",
        "integer_overflow",
        "constraint",
        "migration_shape",
        "migration_order",
        "migration_checksum",
        "duplicate_name",
    ],
)
def test_rechecksummed_invalid_artifact_rolls_back(db, tmp_path, damage):
    path = artifact(tmp_path)
    bundle = json.loads(path.read_text(encoding="utf-8"))
    payload = bundle["payload"]
    doc = next(o for o in payload["objects"] if o["schema"]["op"] == "collection")
    table = next(o for o in payload["objects"] if o["schema"]["op"] == "table")
    if damage == "format_bool":
        payload["format"] = True
    elif damage == "unknown":
        payload["unknown"] = 1
    elif damage == "objects":
        payload["objects"] = {}
    elif damage == "schema":
        doc["schema"]["op"] = "drop"
    elif damage == "rows":
        doc["rows"] = [None]
    elif damage == "version_bool":
        doc["rows"][0]["version"] = True
    elif damage == "version_overflow":
        doc["rows"][0]["version"] = 2**63
    elif damage == "id":
        doc["rows"][0]["id"] = None
    elif damage == "body":
        doc["rows"][0]["body"] = {"x": 2**53}
    elif damage == "duplicate_id":
        doc["rows"].append(doc["rows"][0])
    elif damage == "binary_extra":
        table["rows"][0]["blob"] = {"base64": "", "ignored": 1}
    elif damage == "binary_invalid":
        table["rows"][0]["blob"] = {"base64": "%%%"}
    elif damage == "binary_padbits":
        table["rows"][0]["blob"] = {"base64": "AB=="}
    elif damage == "integer_overflow":
        table["rows"][0]["big"] = 2**63
    elif damage == "constraint":
        doc["schema"]["constraints"] = [{"op": "require", "name": "wrong", "path": ["v"]}]
    elif damage == "migration_shape":
        payload["migrations"][0]["operations"] = "{}"
        payload["migrations"][0]["checksum"] = hashlib.sha256(b"{}").hexdigest()
    elif damage == "migration_order":
        payload["migrations"] *= 2
    elif damage == "migration_checksum":
        payload["migrations"][0]["checksum"] = "wrong"
    elif damage == "duplicate_name":
        payload["objects"].append(doc)
    if isinstance(payload["objects"], list):
        for obj in payload["objects"]:
            obj["checksum"] = checksum(obj["rows"])
    bundle["checksum"] = checksum(payload)
    path.write_bytes(canonical(bundle))
    with pytest.raises(MeldDBError):
        db.import_into(path)
    assert db.inspect()["objects"] == []
    assert db.inspect()["migrations"] == []
    assert db._backend.tables() == []


@pytest.mark.parametrize("content", ['{"payload":{},"payload":{}}', '{"payload":NaN}', "{", "[]"])
def test_malformed_json(db, tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(MeldDBError):
        db.import_into(path)
    assert db._backend.tables() == []


def test_view_only_destination_is_not_empty(db, tmp_path):
    path = artifact(tmp_path)
    db.sql("CREATE VIEW existing AS SELECT 1 AS n")
    with pytest.raises(AlreadyExistsError):
        db.import_into(path)
    assert db.sql("SELECT * FROM existing") == [{"n": 1}]


def test_snapshot_includes_one_committed_state(tmp_path, monkeypatch):
    path = tmp_path / "live.db"
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 50, 7))
    with (melddb.open(path, journal_mode="wal") as source,
          melddb.open(path, journal_mode="wal") as writer):
        fixture(source)
        execute = source._backend.execute
        changed = False

        def interleave(statement, *args, **kwargs):
            nonlocal changed
            result = execute(statement, *args, **kwargs)
            if statement.startswith('SELECT * FROM "ad_') and not changed:
                changed = True
                writer.collection("docs").replace("a", {"v": 99})
            return result

        monkeypatch.setattr(source._backend, "execute", interleave)
        source.export(tmp_path / "snapshot.json")
        assert changed
    with melddb.open(tmp_path / "restored.db") as restored:
        restored.import_into(tmp_path / "snapshot.json")
        assert restored.collection("docs").get("a")["body"] == {"v": 3}


def test_typescript_lossless_reader(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node 22.18+ required for TypeScript proof")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    major, minor, *_ = map(int, version.split("."))
    if not (major >= 24 or (major == 22 and minor >= 18)):
        pytest.skip("Node 22.18 or 24+ required for the TypeScript proof")
    path = artifact(tmp_path)
    reader = Path(__file__).parents[1] / "compat" / "read-export.ts"
    result = subprocess.run(
        [node, str(reader), str(path)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert set(summary["integers"]) == {str(2**63 - 1), str(-(2**63))}
    assert summary["checksums"] == "verified" and summary["binaryBytes"] == 2
    path.write_bytes(path.read_bytes().replace(b'"weight":2', b'"weight":3'))
    result = subprocess.run(
        [node, str(reader), str(path)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode != 0


def test_shared_language_neutral_fixture(db, tmp_path):
    path = Path(__file__).parent / "fixtures" / "logical-export.json"
    db.import_into(path)
    assert db.collection("documents").get("document")["version"] == 2**63 - 1
    assert db.table("measurements").get("minimum")["n"] == -(2**63)
    assert db.table("measurements").get("maximum")["blob"] == b"\x00\xff"
    assert len(db.relationship("contains").edges(db.collection("documents").ref("document"))) == 2
    assert db.check()["ok"]
    db.export(tmp_path / "return.json")
    with melddb.open(tmp_path / "returned.db") as returned:
        returned.import_into(tmp_path / "return.json")
        assert returned.table("measurements").get("minimum")["n"] == -(2**63)
        assert returned.collection("documents").get("document")["version"] == 2**63 - 1


def test_export_lists_native_exclusions(tmp_path):
    with melddb.open(tmp_path / "source.db") as source:
        fixture(source)
        source.sql("CREATE VIEW external_view AS SELECT 1 AS n")
        source.export(tmp_path / "native.json")
    bundle = json.loads((tmp_path / "native.json").read_text(encoding="utf-8"))
    assert {"type": "view", "name": "external_view"} in bundle["payload"]["exclusions"][
        "native_objects"
    ]


def test_raw_nonportable_data_cannot_be_exported(tmp_path):
    with melddb.open(tmp_path / "source.db") as source:
        source.collection("docs").insert({}, id="a")
        name = source.inspect()["objects"][0]["physical"]
        source.sql(f'UPDATE "{name}" SET body=?', ('{"n":9007199254740993}',))
        with pytest.raises(MeldDBError):
            source.export(tmp_path / "invalid.json")
        assert not (tmp_path / "invalid.json").exists()
