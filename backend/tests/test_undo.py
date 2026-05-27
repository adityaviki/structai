from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg
import pytest

from structai.db import runs_repo
from structai.db.ids import new_id
from structai.db.pool import with_database
from structai.db.snapshots import create_snapshot
from structai.settings import get_settings

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _make_completed_run_with_snapshot(
    client: AsyncClient,
    project_name: str,
    *,
    table_value: str,
    started_at: datetime | None = None,
) -> tuple[str, str, str]:
    """Create a project + doc + run, lay down a table, snapshot, mark completed."""

    r = await client.post("/api/projects", json={"name": project_name})
    pid = r.json()["id"]
    db_name = r.json()["db_name"]

    up = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    did = up.json()["id"]

    settings = get_settings()
    # Write a marker row into the project DB to act as "imported data".
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS marker (v text)")
        await conn.execute("DELETE FROM marker")
        await conn.execute("INSERT INTO marker (v) VALUES ($1)", table_value)
    finally:
        await conn.close()

    run_id = new_id()
    snap = f"{db_name}_snap_{run_id[:12].lower()}"
    await runs_repo.create_run(
        run_id=run_id, project_id=pid, document_id=did,
        title="x.csv", instructions=None, auto_mode=False,
    )
    # Snapshot AFTER inserting marker so the snapshot also has `table_value`.
    await create_snapshot(settings=settings, project_db=db_name, snapshot_db=snap)
    if started_at is not None:
        meta = await asyncpg.connect(with_database(settings.pg_url, settings.meta_db_name))
        try:
            await meta.execute(
                "UPDATE import_runs SET started_at = $2 WHERE id = $1", run_id, started_at
            )
        finally:
            await meta.close()
    await runs_repo.set_run_status(
        run_id=run_id, status="completed", progress=100, snapshot_db=snap,
        finished_at=datetime.now(UTC), rows_imported=1, created_tables=["marker"],
    )
    return pid, run_id, db_name


async def _read_marker(db_name: str) -> str:
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        row = await conn.fetchrow("SELECT v FROM marker")
        return row["v"] if row else ""
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_undo_lifo_restores_snapshot(client: AsyncClient) -> None:
    pid, run_id, db_name = await _make_completed_run_with_snapshot(
        client, "Undo solo", table_value="snapshot_value",
    )
    # Mutate the live DB *after* the snapshot to simulate later activity.
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        await conn.execute("UPDATE marker SET v = 'live_value'")
    finally:
        await conn.close()
    assert await _read_marker(db_name) == "live_value"

    r = await client.post(f"/api/runs/{run_id}/undo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reverted"
    assert body["undo_available"] is False

    # Live DB now matches snapshot state.
    assert await _read_marker(db_name) == "snapshot_value"


@pytest.mark.asyncio
async def test_undo_older_run_reverts_later(client: AsyncClient) -> None:
    now = datetime.now(UTC)
    pid, run_a_id, db_name = await _make_completed_run_with_snapshot(
        client, "Undo chain", table_value="state_after_A",
        started_at=now - timedelta(hours=2),
    )
    # Insert "later run" with a different snapshot — we don't need to
    # actually capture its state for this test, just have a row that should
    # be marked reverted-by-side-effect.
    later_run = new_id()
    await runs_repo.create_run(
        run_id=later_run, project_id=pid, document_id=(
            (await client.get(f"/api/projects/{pid}/documents")).json()[0]["id"]
        ),
        title="x.csv", instructions=None, auto_mode=False,
    )
    later_snap = f"{db_name}_snap_{later_run[:12].lower()}"
    await create_snapshot(settings=get_settings(), project_db=db_name, snapshot_db=later_snap)
    # Set started_at to NOW (after A's start) and mark completed.
    meta = await asyncpg.connect(
        with_database(get_settings().pg_url, get_settings().meta_db_name)
    )
    try:
        await meta.execute(
            "UPDATE import_runs SET started_at = $2 WHERE id = $1", later_run, now
        )
    finally:
        await meta.close()
    await runs_repo.set_run_status(
        run_id=later_run, status="completed", progress=100, snapshot_db=later_snap,
        finished_at=now, rows_imported=1, created_tables=["marker"],
    )

    # Undo the older run.
    r = await client.post(f"/api/runs/{run_a_id}/undo")
    assert r.status_code == 200, r.text

    # Both runs should be reverted now.
    a = (await client.get(f"/api/runs/{run_a_id}")).json()
    b = (await client.get(f"/api/runs/{later_run}")).json()
    assert a["status"] == "reverted"
    assert b["status"] == "reverted"
    assert b["reverted_by_run_id"] == run_a_id
