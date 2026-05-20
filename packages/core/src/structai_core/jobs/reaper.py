"""Stale-job reaper.

A job whose `lease_expires_at` has passed had its worker crash or hang.
Re-queue it if attempts remain; otherwise mark it failed so it doesn't
sit `running` forever.

The attempts count is NOT decremented on reap — a crashed claim still
costs one of the budget, otherwise a poison-pill job that crashes the
worker every time would loop indefinitely.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.db.models import Job


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def reap_stale(session: AsyncSession) -> int:
    """Returns the number of jobs reaped (re-queued or marked failed)."""
    now = _now()

    requeued = await session.execute(
        update(Job)
        .where(
            Job.status == "running",
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
            Job.attempts < Job.max_attempts,
        )
        .values(
            status="queued",
            locked_at=None,
            locked_by=None,
            lease_expires_at=None,
            heartbeat_at=None,
        )
        .returning(Job.id)
    )
    requeued_n = len(requeued.all())

    exhausted = await session.execute(
        update(Job)
        .where(
            Job.status == "running",
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
            Job.attempts >= Job.max_attempts,
        )
        .values(
            status="failed",
            finished_at=now,
            error_class="terminal",
            last_error="lease expired after max_attempts; worker likely crashed",
        )
        .returning(Job.id)
    )
    exhausted_n = len(exhausted.all())

    return requeued_n + exhausted_n
