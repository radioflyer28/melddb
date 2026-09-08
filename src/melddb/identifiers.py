"""Stateless RFC 9562 UUIDv7 IDs, identical on Python 3.12–3.14."""
from secrets import randbits
from time import time_ns
from uuid import UUID

from .errors import ValidationError


def new_id():
    milliseconds = time_ns() // 1_000_000
    if not 0 <= milliseconds < 2**48:
        raise ValidationError("Clock is outside the UUIDv7 timestamp range")
    random = randbits(74)
    value = (milliseconds << 80) | (7 << 76) | ((random >> 62) << 64)
    value |= (2 << 62) | (random & ((1 << 62) - 1))
    return str(UUID(int=value))
