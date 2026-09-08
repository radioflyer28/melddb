"""JSON-serializable migration declarations, with no model classes."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    id: str
    operations: tuple


def collection(name):
    return {"op": "collection", "name": name}


def table(name, columns):
    return {"op": "table", "name": name, "columns": columns}


def relationship(name, source, target, *, on_delete="restrict", properties=True):
    return {"op": "relationship", "name": name, "source": source, "target": target,
            "on_delete": on_delete, "properties": properties}


def index(name, *path, unique=False):
    return {"op": "index", "name": name, "path": list(path), "unique": unique}


def require(name, *path):
    return {"op": "require", "name": name, "path": list(path)}


def type_of(name, *path, type):
    return {"op": "type", "name": name, "path": list(path), "type": type}
