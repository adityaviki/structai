from __future__ import annotations

import io
from typing import TYPE_CHECKING

import asyncpg
import pytest

from structai.db import runs_repo
from structai.db.ids import new_id
from structai.settings import get_settings

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _make_project(client: AsyncClient, name: str = "Del") -> tuple[str, str]:
    r = await client.post("/api/projects", json={"name": name})
    j = r.json()
    return j["id"], j["db_name"]


async def _db_exists(name: str) -> bool:
    s = get_settings()
    conn = await asyncpg.connect(s.pg_url)
    try:
        return bool(await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name))
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_delete_project_drops_db(client: AsyncClient) -> None:
    pid, db = await _make_project(client)
    assert await _db_exists(db)
    r = await client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204
    assert not await _db_exists(db)
    r2 = await client.get(f"/api/projects/{pid}")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_project_404(client: AsyncClient) -> None:
    r = await client.delete("/api/projects/missing")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_ok_and_blocked(client: AsyncClient) -> None:
    pid, _ = await _make_project(client, "DocDel")
    up = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    did = up.json()["id"]

    # Unreferenced → delete succeeds.
    r = await client.delete(f"/api/projects/{pid}/documents/{did}")
    assert r.status_code == 204

    # Re-upload + attach an active run; delete is blocked until cancelled/failed.
    up2 = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("y.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    did2 = up2.json()["id"]
    run_id = new_id()
    await runs_repo.create_run(
        run_id=run_id, project_id=pid, document_id=did2,
        title="y.csv", instructions=None, auto_mode=False,
    )
    await runs_repo.set_run_status(run_id=run_id, status="executing")

    r = await client.delete(f"/api/projects/{pid}/documents/{did2}")
    assert r.status_code == 409

    # Mark the run failed → delete now allowed.
    await runs_repo.set_run_status(run_id=run_id, status="failed")
    r = await client.delete(f"/api/projects/{pid}/documents/{did2}")
    assert r.status_code == 204
