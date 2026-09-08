"""Compile the enumerated predicates with type guards and bound values."""
import json

from .backend import literal, quote
from .errors import ValidationError
from .values import Predicate, json_value, text


def path_parts(path):
    if not isinstance(path, (tuple, list)) or not path:
        raise ValidationError("An object-key path is required")
    return tuple(text(key) for key in path)


def json_expr(path, pg=False, column="body"):
    path = path_parts(path)
    col = quote(column)
    if pg:
        args = ",".join(literal(key) for key in path)
        value = f"jsonb_extract_path({col},{args})"
        scalar = f"jsonb_extract_path_text({col},{args})"
        return value, f"jsonb_typeof({value})", scalar
    jp = "$" + "".join("." + json.dumps(key, ensure_ascii=False) for key in path)
    value = f"json_extract({col},{literal(jp)})"
    return value, f"json_type({col},{literal(jp)})", value


def compile_predicate(pred, spec, pg=False):
    if pred is None:
        return "1=1", []
    if not isinstance(pred, Predicate):
        raise ValidationError("Expected a field predicate")
    if pred.op in ("and", "or"):
        parts = [compile_predicate(p, spec, pg) for p in pred.value]
        return "(" + f" {pred.op.upper()} ".join(p[0] for p in parts) + ")", sum(
            (p[1] for p in parts), [])
    if pred.op == "not":
        sql, params = compile_predicate(pred.value, spec, pg)
        return f"NOT ({sql})", params
    if pred.op not in ("eq", "ne", "gt", "gte", "lt", "lte", "in", "null", "missing"):
        raise ValidationError("Unsupported operator")
    path = path_parts(pred.path)
    doc = spec["op"] == "collection"
    if doc:
        value, typ, scalar = json_expr(path, pg)
    else:
        if len(path) != 1 or path[0] not in {"id", *spec["columns"]}:
            raise ValidationError("Unknown table column")
        value = scalar = quote(path[0])
        typ = None
    if pred.op == "missing":
        return (f"{typ} IS NULL" if doc else "1=0"), []
    if pred.op == "null":
        return (f"COALESCE({typ}='null',FALSE)" if doc else f"{value} IS NULL"), []
    if pred.op == "in":
        if not isinstance(pred.value, list) or len(pred.value) > 500:
            raise ValidationError("Membership accepts at most 500 values")
        parts = [compile_predicate(Predicate("eq", path, v), spec, pg) for v in pred.value]
        return ("(" + " OR ".join(p[0] for p in parts) + ")" if parts else "1=0",
                sum((p[1] for p in parts), []))
    v = pred.value
    if isinstance(v, (list, dict)):
        raise ValidationError("Only scalar comparisons are supported")
    if v is None:
        return "1=0", []
    if doc:
        json_value(v)
    if pred.op in ("gt", "gte", "lt", "lte") and type(v) not in (int, float):
        raise ValidationError("Ordered comparisons are numeric only")
    operator = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[pred.op]
    if doc:
        if type(v) is bool:
            guard = f"{typ}='boolean'" if pg else f"{typ} IN ('true','false')"
            expression = f"CAST({scalar} AS BOOLEAN)" if pg else scalar
        elif type(v) in (int, float):
            guard = f"{typ}='number'" if pg else f"{typ} IN ('integer','real')"
            expression = f"CAST({scalar} AS DOUBLE PRECISION)" if pg else scalar
        else:
            guard = f"{typ}='string'" if pg else f"{typ}='text'"
            expression = scalar + (' COLLATE "C"' if pg else ' COLLATE BINARY')
        # CASE prevents invalid casts even if the optimizer reorders predicates.
        return f"(CASE WHEN {guard} THEN {expression} {operator} ? ELSE FALSE END)", [v]
    from .storage import validate_column
    kind = "text" if path[0] == "id" else spec["columns"][path[0]]
    validate_column(kind, v)
    return f"COALESCE({value} {operator} ?,FALSE)", [v]


def ordering(path, spec, pg=False, descending=False):
    if path is None:
        return '"id" ASC'
    path = path.path if hasattr(path, "path") else (path,) if isinstance(path, str) else path
    path = path_parts(path)
    direction = "DESC" if descending else "ASC"
    if spec["op"] == "table":
        if len(path) != 1 or path[0] not in {"id", *spec["columns"]}:
            raise ValidationError("Unknown ordering column")
        val = quote(path[0])
        collation = (' COLLATE "C"' if pg else ' COLLATE BINARY') if (
            path[0] == "id" or spec["columns"].get(path[0]) == "text") else ""
        return f"({val} IS NOT NULL) ASC, {val}{collation} {direction}, id ASC"
    value, typ, scalar = json_expr(path, pg)
    # Type ranks never reverse: missing, null, boolean, number, string, array, object.
    pairs = (("null", 1), ("boolean", 2), ("number", 3), ("string", 4), ("array", 5),
             ("object", 6)) if pg else (("null", 1), ("false", 2), ("true", 2),
             ("integer", 3), ("real", 3), ("text", 4), ("array", 5), ("object", 6))
    rank = "CASE " + " ".join(f"WHEN {typ}={literal(t)} THEN {r}" for t, r in pairs) + " ELSE 0 END"
    if pg:
        num = f"CASE WHEN {typ}='number' THEN CAST({scalar} AS DOUBLE PRECISION) END"
        boolean = f"CASE WHEN {typ}='boolean' THEN CAST({scalar} AS BOOLEAN) END"
        string = f"CASE WHEN {typ}='string' THEN {scalar} END COLLATE \"C\""
    else:
        num = f"CASE WHEN {typ} IN ('integer','real') THEN {value} END"
        boolean = f"CASE WHEN {typ} IN ('true','false') THEN {value} END"
        string = f"CASE WHEN {typ}='text' THEN {value} END COLLATE BINARY"
    return f"{rank} ASC, {boolean} {direction}, {num} {direction}, {string} {direction}, id ASC"
