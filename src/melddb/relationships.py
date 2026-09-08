"""Declared edges and budgeted batched breadth-first reachability."""
import json

from .backend import quote
from .database import physical
from .errors import TraversalLimitError, ValidationError
from .values import Ref, encode, text


class Relationship:
    def __init__(self, scope, name):
        self.scope, self.db, self.name = scope, scope._db, name
        self.sqlname = quote(physical(name))

    def _spec(self):
        return self.db._spec(self.name, "relationship")

    def _ref(self, ref, expected):
        if not isinstance(ref, Ref) or ref.storage != expected or ref._owner != self.db._owner:
            raise ValidationError("Reference belongs to another endpoint or database handle")
        return text(ref.id)

    def connect(self, source, target, properties=None):
        with self.scope._operation(write=True):
            spec = self._spec()
            props = {} if properties is None else properties
            payload = encode(props, object_only=True)
            if props and not spec["properties"]:
                raise ValidationError("This relationship has no properties")
            self.db._backend.execute(f"INSERT INTO {self.sqlname} VALUES (?,?,?)",
                                     (self._ref(source, spec["source"]),
                                      self._ref(target, spec["target"]), payload))

    def disconnect(self, source, target):
        with self.scope._operation(write=True):
            spec = self._spec()
            return bool(self.db._backend.execute(
                f"DELETE FROM {self.sqlname} WHERE source_id=? AND target_id=? RETURNING source_id",
                (self._ref(source, spec["source"]), self._ref(target, spec["target"])))[0])

    def replace_properties(self, source, target, properties):
        with self.scope._operation(write=True):
            spec = self._spec()
            payload = encode(properties, object_only=True)
            if properties and not spec["properties"]:
                raise ValidationError("This relationship has no properties")
            return bool(self.db._backend.execute(
                f"UPDATE {self.sqlname} SET properties=? WHERE source_id=? AND target_id=? RETURNING source_id",
                (payload, self._ref(source, spec["source"]), self._ref(target, spec["target"])))[0])

    def edges(self, ref, *, direction="out", limit=100, offset=0):
        with self.scope._operation():
            spec = self._spec()
            src, dst, start, _ = self._direction(spec, direction)
            if (type(limit) is not int or not 1 <= limit <= 10000 or
                    type(offset) is not int or not 0 <= offset <= 2**63-1):
                raise ValidationError("Invalid pagination")
            collation = 'COLLATE "C"' if self.db._backend.pg else 'COLLATE BINARY'
            rows = self.db._backend.execute(
                f"SELECT * FROM {self.sqlname} WHERE {src}=? ORDER BY {dst} {collation} LIMIT ? OFFSET ?",
                (self._ref(ref, start), limit, offset))[0]
            for row in rows:
                if isinstance(row["properties"], str):
                    row["properties"] = json.loads(row["properties"])
            return rows

    @staticmethod
    def _direction(spec, direction):
        if direction == "out":
            return "source_id", "target_id", spec["source"], spec["target"]
        if direction == "in":
            return "target_id", "source_id", spec["target"], spec["source"]
        raise ValidationError("Direction must be 'in' or 'out'")

    def neighbors(self, ref, *, direction="out", depth=1, max_nodes=10000, max_edges=50000):
        with self.scope._operation():
            spec = self._spec()
            src, dst, start, target = self._direction(spec, direction)
            origin = self._ref(ref, start)
            if any(type(v) is not int or not 1 <= v <= 2**63-2 for v in (depth, max_nodes, max_edges)):
                raise ValidationError("Traversal depth and budgets must be integers in 1..2**63-2")
            # A homogeneous relation can recurse; a heterogeneous one naturally ends after one hop.
            seen, frontier, found, examined = {origin} if start == target else set(), [origin], {}, 0
            origin_count = int(start != target)
            for level in range(1, depth + 1):
                next_frontier = []
                for offset in range(0, len(frontier), 400):
                    chunk = frontier[offset:offset + 400]
                    rows = self.db._backend.execute(
                        f"SELECT {dst} AS id FROM {self.sqlname} WHERE {src} IN "
                        f"({','.join('?' for _ in chunk)}) ORDER BY {src},{dst} LIMIT ?",
                        (*chunk, max_edges - examined + 1))[0]
                    examined += len(rows)
                    if examined > max_edges:
                        raise TraversalLimitError("Examined-edge budget exceeded")
                    for row in rows:
                        ident = row["id"]
                        if ident in seen:
                            continue
                        seen.add(ident)
                        if len(seen) + origin_count > max_nodes:
                            raise TraversalLimitError("Visited-node budget exceeded")
                        found[ident] = level
                        next_frontier.append(ident)
                frontier = next_frontier
                if not frontier or start != target:
                    break
            target_spec = self.db._spec(target)
            from .storage import Collection, Table
            store = (Collection if target_spec["op"] == "collection" else Table)(self.scope, target)
            records = {}
            ids = sorted(found)
            for offset in range(0, len(ids), 400):
                chunk = ids[offset:offset + 400]
                rows = self.db._backend.execute(
                    f"SELECT * FROM {quote(physical(target))} WHERE id IN ({','.join('?' for _ in chunk)})",
                    chunk)[0]
                records.update((row["id"], store._decode(row, target_spec)) for row in rows)
            return [{"ref": Ref(target, ident, self.db._owner), "depth": found[ident],
                     "record": records[ident]} for ident in sorted(found, key=lambda i: (found[i], i))]
