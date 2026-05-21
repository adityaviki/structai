"""Reaper — recycles jobs whose lease has expired."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.db.models import Job
from structai_core.jobs.queue import claim_one, enqueue
from structai_core.jobs.reaper import reap_stale


async def _expire_lease(db_session: AsyncSession, job_id: int) -> None:
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    await db_session.execute(
        update(Job).where(Job.id == job_id).values(lease_expires_at=past)
    )
    await db_session.commit()


async def test_reaper_requeues_when_attempts_remain(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=3)
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await db_session.commit()

    await _expire_lease(db_session, job_id)

    n = await reap_stale(db_session)
    await db_session.commit()
    assert n == 1

    job = await db_session.get(Job, job_id)
    await db_session.refresh(job)
    assert job.status == "queued"
    assert job.locked_by is None
    assert job.locked_at is None
    assert job.lease_expires_at is None
    assert job.heartbeat_at is None
    assert job.attempts == 1  # crashed attempt still counted (no decrement)


async def test_reaper_marks_failed_when_attempts_exhausted(
    db_session: AsyncSession,
) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=1)
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await db_session.commit()

    await _expire_lease(db_session, job_id)

    n = await reap_stale(db_session)
    await db_session.commit()
    assert n == 1

    job = await db_session.get(Job, job_id)
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.error_class == "terminal"
    assert job.last_error is not None
    assert "lease expired" in job.last_error
    assert job.finished_at is not None


async def test_reaper_leaves_live_leases_alone(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=300)
    await db_session.commit()

    n = await reap_stale(db_session)
    await db_session.commit()
    assert n == 0

    job = await db_session.get(Job, job_id)
    assert job.status == "running"


async def test_reaper_no_op_on_empty_queue(db_session: AsyncSession) -> None:
    assert await reap_stale(db_session) == 0


async def test_reaper_handles_mix_of_requeue_and_fail(db_session: AsyncSession) -> None:
    requeue_id = await enqueue(db_session, kind="t", max_attempts=3)
    fail_id = await enqueue(db_session, kind="t", max_attempts=1)
    await db_session.commit()

    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await db_session.commit()

    await _expire_lease(db_session, requeue_id)
    await _expire_lease(db_session, fail_id)

    n = await reap_stale(db_session)
    await db_session.commit()
    assert n == 2

    requeued = await db_session.get(Job, requeue_id)
    failed = await db_session.get(Job, fail_id)
    await db_session.refresh(requeued)
    await db_session.refresh(failed)
    assert requeued.status == "queued"
    assert failed.status == "failed"
    assert failed.error_class == "terminal"
