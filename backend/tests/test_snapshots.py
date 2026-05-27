from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

from structai.db.pool import with_database
from structai.db.pools import get_pools
from structai.db.snapshots import create_snapshot, drop_snapshot, restore_from_snapshot
from structai.settings import get_settings


async def _project_db_for(client: AsyncClient, name: str = "Snap test") -> str:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["db_name"]


async def _insert_marker(db_name: str, value: str) -> None:
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS marker (v text)")
        await conn.execute("DELETE FROM marker")
        await conn.execute("INSERT INTO marker (v) VALUES ($1)", value)
    finally:
        await conn.close()


async def _read_marker(db_name: str) -> str:
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        row = await conn.fetchrow("SELECT v FROM marker")
        return row["v"] if row else ""
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_create_drop_restore(client: AsyncClient) -> None:
    settings = get_settings()
    db = await _project_db_for(client)
    await _insert_marker(db, "before")

    snap = f"{db}_snap_test"
    await create_snapshot(settings=settings, project_db=db, snapshot_db=snap)

    # The snapshot should hold "before"; the live DB still holds "before" too.
    assert await _read_marker(snap) == "before"
    await _insert_marker(db, "after")
    assert await _read_marker(db) == "after"
    assert await _read_marker(snap) == "before"

    await restore_from_snapshot(settings=settings, project_db=db, snapshot_db=snap)
    assert await _read_marker(db) == "before"

    # Snapshot DB no longer exists (it was renamed to the live name).
    admin = await asyncpg.connect(settings.pg_url)
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", snap)
    finally:
        await admin.close()
    assert exists is None

    # Cleanup: drop the resulting project DB so the conftest cleanup is happy.
    await get_pools().drop_project_pool(db)


@pytest.mark.asyncio
async def test_drop_snapshot_idempotent(client: AsyncClient) -> None:
    settings = get_settings()
    # Should not raise.
    await drop_snapshot(settings=settings, snapshot_db="structai_nonexistent_x")
