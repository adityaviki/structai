from __future__ import annotations

import asyncio
import json
from collections.abc import (
    AsyncIterator,  # noqa: TC003 -- used in async generator signature at runtime
)
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..agent.events import channel, publish
from ..db import clarifications_repo, runs_repo
from ..db.ids import new_id
from ..db.pools import get_pools
from ..db.snapshots import drop_snapshot, restore_from_snapshot
from ..logging import log
from ..schemas.run import (
    ClarificationAnswerIn,
    ClarificationOption,
    ClarificationOut,
    ImportRunIn,
    ImportRunOut,
    PipelineStepOut,
)
from ..settings import get_settings
from .errors import ApiError

if TYPE_CHECKING:
    import asyncpg


router = APIRouter(prefix="/api", tags=["runs"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _step_record_to_out(row: asyncpg.Record) -> PipelineStepOut:
    return PipelineStepOut(
        key=row["step_key"],
        title=row["title"],
        status=row["status"],
        summary=row["summary"],
        code=row["code"],
        language=row["language"],
        attempts=row["attempts"],
        errors=list(row["errors"]) if row["errors"] is not None else None,
        started_at=row["started_at"],
        duration_ms=row["duration_ms"],
    )


def _clar_record_to_out(row: asyncpg.Record) -> ClarificationOut:
    raw_options = row["options"]
    if isinstance(raw_options, str):
        raw_options = json.loads(raw_options)
    options = [ClarificationOption(**o) for o in raw_options]
    return ClarificationOut(
        id=row["id"],
        run_id=row["run_id"],
        question=row["question"],
        context=row["context"],
        options=options,
        answer_choice_id=row["answer_choice_id"],
        answer_custom=row["answer_custom"],
        auto_decision=row["auto_decision"],
        auto_reasoning=row["auto_reasoning"],
        created_at=row["created_at"],
        answered_at=row["answered_at"],
    )


async def _row_to_out(row: asyncpg.Record, steps: list[asyncpg.Record]) -> ImportRunOut:
    undo_available = (
        row["status"] == "completed"
        and row["snapshot_db"] is not None
    )
    clar_rows = await clarifications_repo.list_for_run(row["id"])
    return ImportRunOut(
        id=row["id"],
        project_id=row["project_id"],
        document_id=row["document_id"],
        title=row["title"],
        status=row["status"],
        progress=row["progress"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        rows_imported=row["rows_imported"],
        total_rows=row["total_rows"],
        created_tables=list(row["created_tables"]) if row["created_tables"] is not None else None,
        instructions=row["instructions"],
        auto_mode=row["auto_mode"],
        error_message=row["error_message"],
        undo_available=undo_available,
        reverted_at=row["reverted_at"],
        reverted_by_run_id=row["reverted_by_run_id"],
        steps=[_step_record_to_out(s) for s in steps],
        clarifications=[_clar_record_to_out(c) for c in clar_rows],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/imports", response_model=ImportRunOut, status_code=201)
async def create_import(project_id: str, body: ImportRunIn) -> ImportRunOut:
    pools = get_pools()
    meta = await pools.meta()

    async with meta.acquire() as conn:
        project = await conn.fetchrow("SELECT id FROM projects WHERE id = $1", project_id)
        if project is None:
            raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")
        doc = await conn.fetchrow(
            "SELECT * FROM documents WHERE id = $1 AND project_id = $2",
            body.document_id,
            project_id,
        )
        if doc is None:
            raise ApiError(
                status=404,
                title="Not found",
                detail=f"Document {body.document_id!r} not found in project.",
            )

    run_id = new_id()
    await runs_repo.create_run(
        run_id=run_id,
        project_id=project_id,
        document_id=body.document_id,
        title=doc["name"],
        instructions=body.instructions,
        auto_mode=body.auto_mode,
    )

    # Enqueue. arq's job will pick this up; max_jobs=1 enforces serial.
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("import_job", run_id)
    finally:
        await pool.aclose()

    log.info("import.enqueued", run_id=run_id, project_id=project_id)
    run = await runs_repo.get_run(run_id)
    steps = await runs_repo.list_run_steps(run_id)
    assert run is not None
    return await _row_to_out(run, steps)


@router.get("/runs/{run_id}", response_model=ImportRunOut)
async def get_run(run_id: str) -> ImportRunOut:
    run = await runs_repo.get_run(run_id)
    if run is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    steps = await runs_repo.list_run_steps(run_id)
    return await _row_to_out(run, steps)


@router.get("/projects/{project_id}/imports", response_model=list[ImportRunOut])
async def list_imports(project_id: str) -> list[ImportRunOut]:
    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        if await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", project_id) is None:
            raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")

    rows = await runs_repo.list_project_runs(project_id)
    out: list[ImportRunOut] = []
    for row in rows:
        steps = await runs_repo.list_run_steps(row["id"])
        out.append(await _row_to_out(row, steps))
    return out


# ---------------------------------------------------------------------------
# SSE
# ---------------------------------------------------------------------------


async def _event_stream(request: Request, run_id: str) -> AsyncIterator[dict[str, str]]:
    # Send a snapshot first so the UI hydrates without an extra request.
    run = await runs_repo.get_run(run_id)
    if run is None:
        yield {"event": "error", "data": json.dumps({"detail": "run not found"})}
        return
    steps = await runs_repo.list_run_steps(run_id)
    snapshot_obj = await _row_to_out(run, steps)
    yield {
        "event": "snapshot",
        "data": snapshot_obj.model_dump_json(),
    }

    if run["status"] in {"completed", "failed"}:
        # Nothing more to stream — but keep the connection open briefly so
        # the client sees the snapshot before EOF.
        yield {"event": "completed", "data": "{}"}
        return

    settings = get_settings()
    redis: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, decode_responses=True
    )
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(run_id))
    try:
        while True:
            if await request.is_disconnected():
                break
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if msg is None:
                # Heartbeat so proxies don't close idle connections.
                yield {"event": "ping", "data": "{}"}
                continue
            data = msg.get("data")
            if not isinstance(data, str):
                continue
            yield {"event": "message", "data": data}
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                obj = {}
            if obj.get("type") in {"completed", "failed"}:
                # Drain a moment and close.
                await asyncio.sleep(0.05)
                break
    finally:
        await pubsub.unsubscribe(channel(run_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await redis.aclose()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> EventSourceResponse:
    return EventSourceResponse(_event_stream(request, run_id))


@router.post("/runs/{run_id}/restart", response_model=ImportRunOut, status_code=201)
async def restart_run(run_id: str) -> ImportRunOut:
    """Create a fresh run on the same document with the same instructions.

    Only valid when the original run is in a final state (completed,
    failed, cancelled, reverted) — we never run two on one document at once.
    """

    original = await runs_repo.get_run(run_id)
    if original is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    if original["status"] not in {"completed", "failed", "cancelled", "reverted"}:
        raise ApiError(
            status=409,
            title="Run is active",
            detail=f"Cannot restart a {original['status']} run; stop it first.",
        )

    new_run_id = new_id()
    await runs_repo.create_run(
        run_id=new_run_id,
        project_id=original["project_id"],
        document_id=original["document_id"],
        title=original["title"],
        instructions=original["instructions"],
        auto_mode=original["auto_mode"],
    )

    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("import_job", new_run_id)
    finally:
        await pool.aclose()

    log.info("import.restarted", original=run_id, new=new_run_id)
    run = await runs_repo.get_run(new_run_id)
    steps = await runs_repo.list_run_steps(new_run_id)
    assert run is not None
    return await _row_to_out(run, steps)


@router.post("/runs/{run_id}/undo", status_code=200, response_model=ImportRunOut)
async def undo_run(run_id: str) -> ImportRunOut:
    run = await runs_repo.get_run(run_id)
    if run is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    if run["status"] != "completed":
        raise ApiError(
            status=409,
            title="Not undoable",
            detail=f"Only completed runs can be undone (got {run['status']}).",
        )
    if not run["snapshot_db"]:
        raise ApiError(
            status=409,
            title="Snapshot expired",
            detail="The undo snapshot for this run has been removed (retention).",
        )

    settings = get_settings()
    pools = get_pools()
    meta = await pools.meta()

    # Find later runs whose snapshots we'll have to discard. They become
    # logically reverted because we're rewinding past their start times.
    async with meta.acquire() as conn:
        later_rows = await conn.fetch(
            """
            SELECT id, snapshot_db
            FROM import_runs
            WHERE project_id = $1
              AND started_at > $2
              AND status IN ('completed','failed')
            ORDER BY started_at ASC
            """,
            run["project_id"],
            run["started_at"],
        )

    # Restore.
    await restore_from_snapshot(
        settings=settings,
        project_db=run["project_db_name"],
        snapshot_db=run["snapshot_db"],
    )

    # Mark the run reverted, and clear its snapshot (it was just consumed by
    # the rename swap).
    now = datetime.now(UTC)
    await runs_repo.set_run_status(
        run_id=run_id,
        status="reverted",
        reverted_at=now,
        clear_snapshot=True,
    )
    await publish(run_id, {"type": "reverted"})

    # Mark later runs reverted (by side effect) and drop their snapshots.
    for r in later_rows:
        await runs_repo.set_run_status(
            run_id=r["id"],
            status="reverted",
            reverted_at=now,
            reverted_by_run_id=run_id,
            clear_snapshot=True,
        )
        if r["snapshot_db"]:
            try:
                await drop_snapshot(settings=settings, snapshot_db=r["snapshot_db"])
            except Exception:  # noqa: BLE001
                log.exception("undo.later_snapshot_drop_failed", run_id=r["id"])
        await publish(r["id"], {"type": "reverted", "by": run_id})

    refreshed = await runs_repo.get_run(run_id)
    steps = await runs_repo.list_run_steps(run_id)
    assert refreshed is not None
    return await _row_to_out(refreshed, steps)


@router.get("/runs/{run_id}/clarifications", response_model=list[ClarificationOut])
async def list_clarifications(run_id: str) -> list[ClarificationOut]:
    run = await runs_repo.get_run(run_id)
    if run is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    rows = await clarifications_repo.list_for_run(run_id)
    return [_clar_record_to_out(r) for r in rows]


@router.post(
    "/runs/{run_id}/clarifications/{clar_id}/answer",
    response_model=ClarificationOut,
)
async def answer_clarification(
    run_id: str,
    clar_id: str,
    body: ClarificationAnswerIn,
) -> ClarificationOut:
    if not body.choice_id and not body.custom:
        raise ApiError(
            status=400,
            title="Bad request",
            detail="Provide at least one of choice_id or custom.",
        )

    clar = await clarifications_repo.get_clarification(clar_id)
    if clar is None or clar["run_id"] != run_id:
        raise ApiError(
            status=404,
            title="Not found",
            detail=f"Clarification {clar_id!r} not found on run {run_id!r}.",
        )
    if clar["answered_at"] is not None:
        raise ApiError(
            status=409,
            title="Already answered",
            detail="This clarification was already answered.",
        )

    updated = await clarifications_repo.record_user_answer(
        clar_id=clar_id, choice_id=body.choice_id, custom=body.custom,
    )
    if not updated:
        raise ApiError(
            status=409,
            title="Already answered",
            detail="This clarification was already answered.",
        )

    await publish(
        run_id,
        {"type": "clarification_answered", "clarification_id": clar_id, "auto": False},
    )

    refreshed = await clarifications_repo.get_clarification(clar_id)
    assert refreshed is not None
    return _clar_record_to_out(refreshed)


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: str) -> dict[str, str]:
    run = await runs_repo.get_run(run_id)
    if run is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    if run["status"] in {"completed", "failed", "cancelled", "reverted"}:
        raise ApiError(
            status=409,
            title="Run is final",
            detail=f"Cannot cancel a {run['status']} run.",
        )
    updated = await runs_repo.request_cancel(run_id)
    if updated:
        # Surface "cancelling" in the UI immediately; the worker will flip to
        # "cancelled" once cleanup completes.
        await runs_repo.set_run_status(run_id=run_id, status="cancelling")
        await publish(run_id, {"type": "run_status", "status": "cancelling"})
    return {"status": "cancelling"}
