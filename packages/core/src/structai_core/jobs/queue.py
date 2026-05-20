"""Postgres-backed job queue primitives.

The queue uses `SELECT … FOR UPDATE SKIP LOCKED` to let many workers claim
disjoint rows without contention. Leases are tracked on the `jobs` row:
`locked_at`, `locked_by`, `lease_expires_at`, `heartbeat_at`.

Lifecycle:
    enqueue → queued
    claim_one → running (attempts += 1, lease set)
    heartbeat → lease extended
    complete → completed
    fail (retryable, attempts < max) → queued (claimable again)
    fail (terminal, or attempts == max) → failed
    cancel / lease-expired-and-out-of-attempts → cancelled / failed (via reaper)

Idempotency:
    enqueue(idempotency_key=…) inserts ON CONFLICT DO NOTHING and returns the
    existing row's id if the key collides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.db.models import Job


@dataclass(frozen=True, slots=True)
class JobClaim:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    worker_id: str
    cancel_requested: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue(
    session: AsyncSession,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> int:
    """Insert a job; if `idempotency_key` collides, return the existing row's id."""
    payload = payload or {}

    if idempotency_key is None:
        job = Job(kind=kind, payload_jsonb=payload, max_attempts=max_attempts)
        session.add(job)
        await session.flush()
        return job.id

    stmt = (
        pg_insert(Job)
        .values(
            kind=kind,
            payload_jsonb=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Job.id)
    )
    res = await session.execute(stmt)
    row = res.first()
    if row is not None:
        return row.id

    existing = await session.execute(
        select(Job.id).where(Job.idempotency_key == idempotency_key)
    )
    return existing.scalar_one()


async def claim_one(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_secs: int,
    kinds: list[str] | None = None,
) -> JobClaim | None:
    """Pick one queued job (FOR UPDATE SKIP LOCKED), transition to running."""
    now = _now()
    lease_expires_at = now + timedelta(seconds=lease_secs)

    stmt = (
        select(Job)
        .where(Job.status == "queued", Job.attempts < Job.max_attempts)
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if kinds is not None:
        stmt = stmt.where(Job.kind.in_(kinds))

    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        return None

    job.status = "running"
    job.locked_at = now
    job.locked_by = worker_id
    job.lease_expires_at = lease_expires_at
    job.heartbeat_at = now
    job.attempts = job.attempts + 1
    await session.flush()

    return JobClaim(
        id=job.id,
        kind=job.kind,
        payload=dict(job.payload_jsonb),
        attempts=job.attempts,
        worker_id=worker_id,
        cancel_requested=bool(job.cancel_requested),
    )


async def heartbeat(
    session: AsyncSession,
    job_id: int,
    *,
    worker_id: str,
    lease_secs: int,
) -> tuple[bool, bool]:
    """Refresh `heartbeat_at` + extend `lease_expires_at`.

    Returns `(still_owned, cancel_requested)`:
      - `still_owned=False` means another process (reaper, manual cancel) took
        the lock — the worker should abandon the task.
      - `cancel_requested=True` means a cooperative cancel was requested; the
        worker should signal the task's `CancellationToken`.
    """
    now = _now()
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.status == "running",
            Job.locked_by == worker_id,
        )
        .values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_secs),
        )
        .returning(Job.cancel_requested)
    )
    res = await session.execute(stmt)
    row = res.first()
    if row is None:
        return (False, False)
    return (True, bool(row.cancel_requested))


async def complete(session: AsyncSession, job_id: int, *, worker_id: str) -> None:
    now = _now()
    await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id)
        .values(
            status="completed",
            finished_at=now,
            last_error=None,
            error_class=None,
        )
    )


async def fail(
    session: AsyncSession,
    job_id: int,
    *,
    worker_id: str,
    error: str,
    error_class: str,
) -> None:
    """Record a failure.

    Retryable + attempts < max → back to `queued` for another claim.
    Otherwise → `failed` (terminal).
    """
    now = _now()
    job = await session.get(Job, job_id)
    if job is None or job.locked_by != worker_id:
        return

    job.last_error = error
    job.error_class = error_class

    if error_class == "retryable" and job.attempts < job.max_attempts:
        job.status = "queued"
        job.locked_at = None
        job.locked_by = None
        job.lease_expires_at = None
        job.heartbeat_at = None
    else:
        job.status = "failed"
        job.finished_at = now


async def cancel(session: AsyncSession, job_id: int, *, worker_id: str | None = None) -> None:
    """Mark cancelled. `worker_id` is checked when the worker itself is finalizing
    a cooperatively-cancelled job; external callers (e.g. an API cancel route)
    pass None."""
    now = _now()
    stmt = update(Job).where(Job.id == job_id).values(status="cancelled", finished_at=now)
    if worker_id is not None:
        stmt = stmt.where(Job.locked_by == worker_id)
    await session.execute(stmt)


async def request_cancel(session: AsyncSession, job_id: int) -> None:
    """Set the cooperative cancel flag. The worker honors it at step boundaries
    (plan §8.4)."""
    await session.execute(
        update(Job).where(Job.id == job_id).values(cancel_requested=True)
    )
