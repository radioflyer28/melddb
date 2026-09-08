"""Portable values and explicitly bounded query expressions."""
import json
import math
from dataclasses import dataclass

from .errors import ValidationError


def text(value):
    if not isinstance(value, str) or "\x00" in value:
        raise ValidationError("Expected a string without NUL")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise ValidationError("String contains an unpaired surrogate") from exc
    return value


def json_value(value):
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > 2**53 - 1:
            raise ValidationError("JSON integer is outside the interoperable range")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("Non-finite JSON number")
    elif isinstance(value, str):
        text(value)
    elif isinstance(value, list):
        for item in value:
            json_value(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            text(key)
            json_value(item)
    else:
        raise ValidationError(f"Unsupported JSON value: {type(value).__name__}")


def encode(value, *, object_only=False):
    if object_only and not isinstance(value, dict):
        raise ValidationError("Document/properties must be an object")
    try:
        json_value(value)
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":"))
    except (RecursionError, ValueError) as exc:
        raise ValidationError("Invalid or cyclic JSON") from exc


@dataclass(frozen=True)
class Ref:
    storage: str
    id: str
    _owner: str


@dataclass(frozen=True)
class Predicate:
    op: str
    path: tuple = ()
    value: object = None

    def __and__(self, other):
        return Predicate("and", value=(self, other))

    def __or__(self, other):
        return Predicate("or", value=(self, other))

    def __invert__(self):
        return Predicate("not", value=self)


@dataclass(frozen=True)
class Field:
    path: tuple

    def eq(self, value):
        return Predicate("eq", self.path, value)

    def ne(self, value):
        return Predicate("ne", self.path, value)

    def gt(self, value):
        return Predicate("gt", self.path, value)

    def gte(self, value):
        return Predicate("gte", self.path, value)

    def lt(self, value):
        return Predicate("lt", self.path, value)

    def lte(self, value):
        return Predicate("lte", self.path, value)

    def isin(self, values):
        return Predicate("in", self.path, list(values))

    def is_null(self):
        return Predicate("null", self.path)

    def is_missing(self):
        return Predicate("missing", self.path)


def field(*keys):
    if not keys:
        raise ValidationError("A field needs at least one object key")
    return Field(tuple(text(key) for key in keys))
