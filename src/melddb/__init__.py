"""Plain values and explicit I/O for embedded application data."""
from . import errors, schema
from .database import Database
from .schema import Migration
from .values import Ref, field

__all__ = ["open", "connect", "Database", "Migration", "Ref", "field", "schema", "errors"]


def open(path, *, timeout=5, readonly=False, journal_mode=None):
    return Database(path, timeout=timeout, readonly=readonly, journal_mode=journal_mode)


def connect(url, *, timeout=5, readonly=False):
    return Database(url, postgres=True, timeout=timeout, readonly=readonly)
