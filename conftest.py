"""Top-level pytest fixtures for the StructAI test suite.

Session scope (autouse):
    - sets `DATABASE_URL` / `DATABASE_URL_SYNC` to the dedicated `structai_test`
      database so the dev DB is never touched
    - drops + recreates `structai_test` so every session starts clean
    - runs Alembic migrations to head once

Function scope:
    - `engine`         — fresh `AsyncEngine` per test (no shared pool — keeps the
                         event-loop story simple under `pytest-asyncio` auto mode)
    - `sessionmaker`   — `async_sessionmaker` bound to that engine
    - `db_session`     — TRUNCATE all data tables, then yield an `AsyncSession`

We TRUNCATE between tests instead of using transaction-per-test rollback because
the queue tests need real concurrent transactions (FOR UPDATE SKIP LOCKED can't
skip rows it owns in the same transaction).

Override the Postgres connection by setting `STRUCTAI_TEST_PG_{HOST,PORT,USER,PASS}`
before invoking pytest. Defaults match `docker-compose.yml`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TEST_DB_NAME = "structai_test"
PG_HOST = os.environ.get("STRUCTAI_TEST_PG_HOST", "localhost")
PG_PORT = os.environ.get("STRUCTAI_TEST_PG_PORT", "5432")
PG_USER = os.environ.get("STRUCTAI_TEST_PG_USER", "structai")
PG_PASS = os.environ.get("STRUCTAI_TEST_PG_PASS", "structai")

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{TEST_DB_NAME}"
)
TEST_DATABASE_URL_SYNC = (
    f"postgresql+psycopg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{TEST_DB_NAME}"
)
ADMIN_DSN = (
    f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASS} dbname=postgres"
)

# Every user-data table in §4. Truncate-restart-identity-cascade between tests.
ALL_TABLES = (
    "rejected_row_artifacts",
    "import_run_tables",
    "import_runs",
    "pipeline_registry",
    "pipeline_artifacts",
    "pipeline_revisions",
    "event_cursors",
    "event_log",
    "agent_sessions",
    "profiles",
    "files",
    "jobs",
)


def _drop_and_create_test_db() -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (TEST_DB_NAME,),
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
        cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')


@pytest.fixture(scope="session", autouse=True)
def _setup_test_database() -> None:
    """Create + migrate `structai_test` once per pytest session."""
    _drop_and_create_test_db()

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["DATABASE_URL_SYNC"] = TEST_DATABASE_URL_SYNC
    os.environ.setdefault("STRUCTAI_USER_SCHEMA", "structai_user")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(TEST_DATABASE_URL, future=True, pool_size=4)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def db_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Truncate all data tables, then yield a fresh session."""
    async with sessionmaker() as cleanup:
        await cleanup.execute(
            text(f"TRUNCATE TABLE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE")
        )
        await cleanup.commit()

    async with sessionmaker() as session:
        yield session
