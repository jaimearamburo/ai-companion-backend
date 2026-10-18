"""Database tests run against a real Postgres with the migrations applied.

They need TEST_DATABASE_URL (CI's migrations job sets it) and are skipped
without it. Each test runs in a transaction that is rolled back, so tests never
see each other's rows.
"""

import os
from collections.abc import AsyncIterator

import pytest
from psycopg import AsyncConnection
from psycopg.rows import TupleRow


@pytest.fixture
async def db() -> AsyncIterator[AsyncConnection[TupleRow]]:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    conn = await AsyncConnection.connect(url)
    try:
        yield conn
    finally:
        await conn.rollback()
        await conn.close()
