import os

import pytest

import melddb


@pytest.fixture(params=["sqlite", "postgres"] if os.getenv("MELDDB_TEST_POSTGRES") else ["sqlite"])
def db(request, tmp_path):
    if request.param == "postgres":
        import uuid

        import psycopg
        namespace = "test_" + uuid.uuid4().hex
        admin = psycopg.connect(os.environ["MELDDB_TEST_POSTGRES"], autocommit=True)
        admin.execute(f'CREATE SCHEMA "{namespace}"')
        from psycopg.conninfo import make_conninfo
        try:
            with melddb.connect(make_conninfo(os.environ["MELDDB_TEST_POSTGRES"],
                                               options=f"-c search_path={namespace}")) as database:
                yield database
        finally:
            try:
                admin.execute(f'DROP SCHEMA "{namespace}" CASCADE')
            finally:
                admin.close()
    else:
        with melddb.open(tmp_path / "db.sqlite") as database:
            yield database
