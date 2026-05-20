"""Per-job heartbeat task.

Spawned alongside a running task. Refreshes `jobs.lease_expires_at` so the
reaper doesn't recycle the row, and flips the task's `CancellationToken`
if `jobs.cancel_requested` becomes true or if the worker loses ownership
(plan §4 lease invariants).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from structai_core.db.session import session_scope
from structai_core.jobs import CancellationToken
from structai_core.jobs.queue import heartbeat

log = logging.getLogger("structai_worker.lease")


async def run_heartbeat(
    sessionmaker: async_sessionmaker,
    *,
    job_id: int,
    worker_id: str,
    heartbeat_secs: int,
    lease_secs: int,
    token: CancellationToken,
    stop: asyncio.Event,
) -> None:
    """Run until `stop` is set or the lease is lost."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=heartbeat_secs)
            return
        except asyncio.TimeoutError:
            pass

        try:
            async with session_scope(sessionmaker) as session:
                still_owned, cancel_requested = await heartbeat(
                    session, job_id, worker_id=worker_id, lease_secs=lease_secs
                )
        except Exception:
            log.exception("heartbeat failure for job %s", job_id)
            continue

        if not still_owned:
            log.warning("lost lease for job %s; signalling cancellation", job_id)
            token.cancel()
            return

        if cancel_requested:
            log.info("cancellation requested for job %s; signalling token", job_id)
            token.cancel()
            return
