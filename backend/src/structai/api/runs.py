from __future__ import annotations

import asyncio
import json
from collections.abc import (
    AsyncIterator,  # noqa: TC003 -- used in async generator signature at runtime
)
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..agent.events import channel
from ..db import runs_repo
from ..db.ids import new_id
from ..db.pools import get_pools
from ..logging import log
from ..schemas.run import ImportRunIn, ImportRunOut, PipelineStepOut
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


def _run_record_to_out(row: asyncpg.Record, steps: list[asyncpg.Record]) -> ImportRunOut:
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
        steps=[_step_record_to_out(s) for s in steps],
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
    return _run_record_to_out(run, steps)


@router.get("/runs/{run_id}", response_model=ImportRunOut)
async def get_run(run_id: str) -> ImportRunOut:
    run = await runs_repo.get_run(run_id)
    if run is None:
        raise ApiError(status=404, title="Not found", detail=f"Run {run_id!r} not found.")
    steps = await runs_repo.list_run_steps(run_id)
    return _run_record_to_out(run, steps)


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
        # Re-fetch with joins so we have the join fields; for list view we can
        # skip join columns since the serializer doesn't need them.
        out.append(
            ImportRunOut(
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
                steps=[_step_record_to_out(s) for s in steps],
            )
        )
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
    yield {
        "event": "snapshot",
        "data": _run_record_to_out(run, steps).model_dump_json(),
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
