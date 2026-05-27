from __future__ import annotations

import asyncio
import os
import tempfile

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

# Use a separate meta DB for tests so we never touch the dev one.
TEST_META_DB = "structai_meta_test"
os.environ.setdefault("STRUCTAI_PG_URL", "postgresql:///postgres")
os.environ["STRUCTAI_META_DB_NAME"] = TEST_META_DB
# Suppress LLM key warning during tests.
os.environ.setdefault("STRUCTAI_ANTHROPIC_API_KEY", "sk-test")
# Quarantine workspace writes inside a temp dir.
_WORKSPACE_TMP = tempfile.mkdtemp(prefix="structai-tests-")
os.environ["STRUCTAI_WORKSPACE"] = _WORKSPACE_TMP

from typing import TYPE_CHECKING  # noqa: E402

from structai.db.migrate import migrate  # noqa: E402
from structai.db.pool import connect_admin, with_database  # noqa: E402
from structai.main import create_app  # noqa: E402
from structai.settings import get_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _reset_test_meta() -> None:
    """Wipe everything the test suite created. Never touches dev databases.

    Discovers project DBs to drop by reading them out of the test meta DB's
    `projects.db_name` rows. If the test meta DB doesn't yet exist, there are
    no project DBs to clean up.
    """

    settings = get_settings()
    admin = await connect_admin(settings)
    try:
        test_meta_exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_META_DB
        )
        if test_meta_exists:
            meta_conn = await asyncpg.connect(with_database(settings.pg_url, TEST_META_DB))
            try:
                rows = await meta_conn.fetch("SELECT db_name FROM projects")
                names = [r["db_name"] for r in rows]
            finally:
                await meta_conn.close()
            for name in names:
                await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
            await admin.execute(f'DROP DATABASE IF EXISTS "{TEST_META_DB}"')
    finally:
        await admin.close()
    await migrate(settings)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    return asyncio.new_event_loop()


@pytest.fixture(autouse=True)
async def _reset_meta() -> AsyncIterator[None]:
    await _reset_test_meta()
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),  # type: ignore[attr-defined]
        AsyncClient(transport=transport, base_url="http://test") as c,
    ):
        yield c
