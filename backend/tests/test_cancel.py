from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from structai.db import runs_repo
from structai.db.ids import new_id

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _setup_run(client: AsyncClient, *, status: str = "executing") -> str:
    """Create a project+doc+run row directly in the meta DB (no worker)."""
    r = await client.post("/api/projects", json={"name": "Cancel"})
    pid = r.json()["id"]
    # Insert a fake document row through API
    import io

    up = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    did = up.json()["id"]
    run_id = new_id()
    await runs_repo.create_run(
        run_id=run_id,
        project_id=pid,
        document_id=did,
        title="x.csv",
        instructions=None,
        auto_mode=False,
    )
    await runs_repo.set_run_status(run_id=run_id, status=status)
    return run_id


@pytest.mark.asyncio
async def test_cancel_active_run(client: AsyncClient) -> None:
    run_id = await _setup_run(client, status="executing")
    r = await client.post(f"/api/runs/{run_id}/cancel")
    assert r.status_code == 202, r.text

    snapshot = await client.get(f"/api/runs/{run_id}")
    assert snapshot.json()["status"] == "cancelling"
    assert await runs_repo.cancel_requested(run_id) is True


@pytest.mark.asyncio
async def test_cancel_completed_run_rejected(client: AsyncClient) -> None:
    run_id = await _setup_run(client, status="completed")
    r = await client.post(f"/api/runs/{run_id}/cancel")
    assert r.status_code == 409
