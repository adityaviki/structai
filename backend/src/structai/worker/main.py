from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from ..db.pools import get_pools, init_pools
from ..logging import configure_logging, log
from ..pipeline.orchestrator import run_import
from ..settings import get_settings
from .sweeper import recover_interrupted_runs, sweep_snapshots


async def noop(_ctx: dict[str, Any]) -> str:
    """Phase 0 sanity job: proves the worker can pick up jobs from Redis."""

    log.info("worker.noop.fired")
    return "ok"


async def import_job(_ctx: dict[str, Any], run_id: str) -> None:
    """Phase 1 entry: run the import pipeline for a single run."""

    log.info("worker.import.start", run_id=run_id)
    await run_import(run_id)
    log.info("worker.import.done", run_id=run_id)


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    init_pools(get_settings())
    log.info("worker.startup")
    # Clean up any runs left in active states by a crashed/killed worker.
    try:
        await recover_interrupted_runs(ctx)
    except Exception:  # noqa: BLE001
        log.exception("worker.startup.recover_failed")


async def shutdown(_ctx: dict[str, Any]) -> None:
    await get_pools().close()
    log.info("worker.shutdown")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """arq entry point. Run with: `arq structai.worker.main.WorkerSettings`."""

    functions = (noop, import_job)
    cron_jobs = [cron(sweep_snapshots, minute=0, run_at_startup=False)]  # type: ignore[arg-type]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 1  # D9: one import at a time
    redis_settings = _redis_settings()
    # The orchestrator suspends on Postgres polls while waiting for the
    # user to answer a clarification or accept a schema proposal. arq's
    # default 5-minute job_timeout cancels the job underneath us in that
    # state, leaving the run pinned in awaiting_* with nobody polling.
    # 8 hours covers realistic human-in-the-loop latency; the polling
    # loop's own cancel/wait-cap (orchestrator._run_schema_approval_loop
    # and _make_clarification_handler) handles genuinely abandoned runs.
    job_timeout = 8 * 3600
