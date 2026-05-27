from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter

from ..settings import get_settings

router = APIRouter()


@router.post("/_dev/enqueue-noop")
async def enqueue_noop() -> dict[str, str]:
    """Dev-only: enqueue the no-op worker job to verify the queue path."""

    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await pool.enqueue_job("noop")
    finally:
        await pool.aclose()
    return {"job_id": job.job_id if job else ""}
