"""Plain values and explicit I/O for embedded application data."""
from . import errors, schema
from .database import Database
from .schema import Migration
from .values import Ref, field

__all__ = ["open", "connect", "Database", "Migration", "Ref", "field", "schema", "errors"]


def open(path, *, timeout=5, readonly=False):
    return Database(path, timeout=timeout, readonly=readonly)


def connect(url, *, timeout=5):
    return Database(url, postgres=True, timeout=timeout)
