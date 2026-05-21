"""Worker entrypoint.

Polls `jobs` with `FOR UPDATE SKIP LOCKED`, leases a job, dispatches it
through the task registry, runs the heartbeat alongside, and finalizes
(complete / fail / cancel) when the task returns or raises.

A separate background loop reaps jobs whose lease has expired (workers
that crashed or hung); see `structai_core.jobs.reaper`.

Default tunables live in `Settings`:
    STRUCTAI_WORKER_HEARTBEAT_SECS=10
    STRUCTAI_WORKER_LEASE_SECS=60
    STRUCTAI_WORKER_POLL_INTERVAL_SECS=1
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket

from structai_core.config import Settings
from structai_core.db.session import make_engine, make_sessionmaker, session_scope
from structai_core.jobs import (
    CancellationToken,
    JobClaim,
    RetryableError,
    TerminalError,
)
from structai_core.jobs.cancellation import JobCancelled
from structai_core.jobs.queue import cancel, claim_one, complete, fail
from structai_core.jobs.reaper import reap_stale

from structai_worker import tasks_profile  # noqa: F401  — registers profile_file
from structai_worker.lease import run_heartbeat
from structai_worker.tasks import dispatch

log = logging.getLogger("structai_worker")

WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"
REAPER_INTERVAL_SECS = 30


async def _process_one(sessionmaker, claim: JobClaim, settings: Settings) -> None:
    token = CancellationToken()
    if claim.cancel_requested:
        token.cancel()

    stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        run_heartbeat(
            sessionmaker,
            job_id=claim.id,
            worker_id=claim.worker_id,
            heartbeat_secs=settings.worker_heartbeat_secs,
            lease_secs=settings.worker_lease_secs,
            token=token,
            stop=stop,
        ),
        name=f"heartbeat-{claim.id}",
    )

    try:
        try:
            async with session_scope(sessionmaker) as session:
                await dispatch(session, claim.kind, claim.payload, token)
        except JobCancelled:
            log.info("job %s (%s) cancelled cooperatively", claim.id, claim.kind)
            async with session_scope(sessionmaker) as session:
                await cancel(session, claim.id, worker_id=claim.worker_id)
            return
        except TerminalError as exc:
            log.error("job %s (%s) terminal: %s", claim.id, claim.kind, exc)
            async with session_scope(sessionmaker) as session:
                await fail(
                    session,
                    claim.id,
                    worker_id=claim.worker_id,
                    error=str(exc),
                    error_class="terminal",
                )
            return
        except RetryableError as exc:
            log.warning("job %s (%s) retryable: %s", claim.id, claim.kind, exc)
            async with session_scope(sessionmaker) as session:
                await fail(
                    session,
                    claim.id,
                    worker_id=claim.worker_id,
                    error=str(exc),
                    error_class="retryable",
                )
            return
        except Exception as exc:  # noqa: BLE001 — fail closed on retryable
            log.exception("job %s (%s) unexpected failure", claim.id, claim.kind)
            async with session_scope(sessionmaker) as session:
                await fail(
                    session,
                    claim.id,
                    worker_id=claim.worker_id,
                    error=repr(exc),
                    error_class="retryable",
                )
            return

        async with session_scope(sessionmaker) as session:
            await complete(session, claim.id, worker_id=claim.worker_id)
        log.info("job %s (%s) completed", claim.id, claim.kind)
    finally:
        stop.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


async def _reaper_loop(sessionmaker, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with session_scope(sessionmaker) as session:
                n = await reap_stale(session)
            if n:
                log.info("reaped %d stale job(s)", n)
        except Exception:
            log.exception("reaper error")

        try:
            await asyncio.wait_for(stop.wait(), timeout=REAPER_INTERVAL_SECS)
        except asyncio.TimeoutError:
            continue


async def run() -> None:
    settings = Settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)

    log.info("worker %s booted", WORKER_ID)
    reaper_task = asyncio.create_task(_reaper_loop(sessionmaker, stop), name="reaper")

    try:
        while not stop.is_set():
            try:
                async with session_scope(sessionmaker) as session:
                    claim = await claim_one(
                        session,
                        worker_id=WORKER_ID,
                        lease_secs=settings.worker_lease_secs,
                    )
            except Exception:
                log.exception("claim_one failure")
                claim = None

            if claim is None:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=settings.worker_poll_interval_secs
                    )
                except asyncio.TimeoutError:
                    pass
                continue

            log.info("claimed job %s (%s) attempt=%d", claim.id, claim.kind, claim.attempts)
            await _process_one(sessionmaker, claim, settings)
    finally:
        stop.set()
        reaper_task.cancel()
        try:
            await reaper_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
