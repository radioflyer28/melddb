"""Connection setup must preserve stable errors and release acquired resources."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import melddb
from melddb.errors import ConnectionError


class DriverError(Exception):
    pass


@pytest.mark.parametrize("stage", ["connect", "configure"])
def test_postgres_setup_failure(monkeypatch, stage):
    error = DriverError("server unavailable")
    connection = Mock()
    connect = Mock(return_value=connection)
    if stage == "connect":
        connect.side_effect = error
    else:
        connection.execute.side_effect = error
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(
        Error=DriverError, connect=connect,
    ))
    with pytest.raises(ConnectionError) as caught:
        melddb.connect("postgresql://unused")
    assert caught.value.__cause__ is error
    if stage == "configure":
        connection.close.assert_called_once()
    else:
        connection.close.assert_not_called()
