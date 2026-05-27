"""Snapshot dashboard endpoints (Phase 6)."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 -- used at runtime by Pydantic field

from fastapi import APIRouter
from pydantic import BaseModel

from ..db.pool import connect_admin
from ..db.pools import get_pools
from ..db.snapshots import drop_snapshot
from ..logging import log
from ..settings import get_settings
from .errors import ApiError

router = APIRouter(prefix="/api/projects/{project_id}/snapshots", tags=["snapshots"])


class SnapshotOut(BaseModel):
    run_id: str
    snapshot_db: str
    finished_at: datetime | None
    pinned: bool
    size_bytes: int


@router.get("", response_model=list[SnapshotOut])
async def list_snapshots(project_id: str) -> list[SnapshotOut]:
    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        if await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", project_id) is None:
            raise ApiError(
                status=404, title="Not found", detail=f"Project {project_id!r} not found."
            )
        rows = await conn.fetch(
            """
            SELECT id, snapshot_db, snapshot_pinned, finished_at
            FROM import_runs
            WHERE project_id = $1 AND snapshot_db IS NOT NULL
            ORDER BY finished_at DESC NULLS LAST, started_at DESC
            """,
            project_id,
        )

    if not rows:
        return []

    # Look up sizes for all referenced DBs in one shot against the cluster.
    settings = get_settings()
    admin = await connect_admin(settings)
    try:
        size_rows = await admin.fetch(
            "SELECT datname, pg_database_size(datname) AS bytes "
            "FROM pg_database WHERE datname = ANY($1::text[])",
            [r["snapshot_db"] for r in rows],
        )
    finally:
        await admin.close()
    sizes = {sr["datname"]: int(sr["bytes"]) for sr in size_rows}

    return [
        SnapshotOut(
            run_id=r["id"],
            snapshot_db=r["snapshot_db"],
            finished_at=r["finished_at"],
            pinned=r["snapshot_pinned"],
            size_bytes=sizes.get(r["snapshot_db"], 0),
        )
        for r in rows
    ]


@router.post("/{run_id}/pin", response_model=SnapshotOut)
async def toggle_pin(project_id: str, run_id: str) -> SnapshotOut:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT snapshot_db, snapshot_pinned, finished_at FROM import_runs "
            "WHERE id = $1 AND project_id = $2 AND snapshot_db IS NOT NULL",
            run_id,
            project_id,
        )
        if row is None:
            raise ApiError(
                status=404,
                title="Not found",
                detail="No snapshot found for that run.",
            )
        new_pinned = not row["snapshot_pinned"]
        await conn.execute(
            "UPDATE import_runs SET snapshot_pinned = $2 WHERE id = $1", run_id, new_pinned
        )

    settings = get_settings()
    admin = await connect_admin(settings)
    try:
        bytes_ = await admin.fetchval(
            "SELECT pg_database_size($1)", row["snapshot_db"]
        )
    finally:
        await admin.close()

    return SnapshotOut(
        run_id=run_id,
        snapshot_db=row["snapshot_db"],
        finished_at=row["finished_at"],
        pinned=new_pinned,
        size_bytes=int(bytes_ or 0),
    )


@router.delete("/{run_id}", status_code=204)
async def delete_snapshot(project_id: str, run_id: str) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT snapshot_db FROM import_runs "
            "WHERE id = $1 AND project_id = $2 AND snapshot_db IS NOT NULL",
            run_id,
            project_id,
        )
        if row is None:
            raise ApiError(
                status=404,
                title="Not found",
                detail="No snapshot found for that run.",
            )
        await conn.execute(
            "UPDATE import_runs SET snapshot_db = NULL, snapshot_pinned = false WHERE id = $1",
            run_id,
        )

    try:
        await drop_snapshot(settings=get_settings(), snapshot_db=row["snapshot_db"])
    except Exception:  # noqa: BLE001
        log.exception("snapshot.delete_failed", snapshot_db=row["snapshot_db"])
