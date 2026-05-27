from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from ..db.pools import get_pools, init_pools
from ..logging import configure_logging, log
from ..pipeline.orchestrator import run_import
from ..settings import get_settings


async def noop(_ctx: dict[str, Any]) -> str:
    """Phase 0 sanity job: proves the worker can pick up jobs from Redis."""

    log.info("worker.noop.fired")
    return "ok"


async def import_job(_ctx: dict[str, Any], run_id: str) -> None:
    """Phase 1 entry: run the import pipeline for a single run."""

    log.info("worker.import.start", run_id=run_id)
    await run_import(run_id)
    log.info("worker.import.done", run_id=run_id)


async def startup(_ctx: dict[str, Any]) -> None:
    configure_logging()
    init_pools(get_settings())
    log.info("worker.startup")


async def shutdown(_ctx: dict[str, Any]) -> None:
    await get_pools().close()
    log.info("worker.shutdown")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """arq entry point. Run with: `arq structai.worker.main.WorkerSettings`."""

    functions = (noop, import_job)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 1  # D9: one import at a time
    redis_settings = _redis_settings()
