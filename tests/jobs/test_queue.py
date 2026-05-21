"""Job queue primitives — enqueue, claim_one, heartbeat, complete, fail, cancel."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from structai_core.db.models import Job
from structai_core.jobs.queue import (
    cancel,
    claim_one,
    complete,
    enqueue,
    fail,
    heartbeat,
    request_cancel,
)


async def test_enqueue_returns_id(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t", payload={"x": 1})
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job is not None
    assert job.kind == "t"
    assert job.payload_jsonb == {"x": 1}
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.max_attempts == 3  # default


async def test_enqueue_persists_max_attempts(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=7)
    await db_session.commit()
    job = await db_session.get(Job, job_id)
    assert job.max_attempts == 7


async def test_enqueue_idempotency_dedup(db_session: AsyncSession) -> None:
    a = await enqueue(db_session, kind="t", idempotency_key="k1")
    b = await enqueue(db_session, kind="t", idempotency_key="k1")
    await db_session.commit()
    assert a == b


async def test_enqueue_distinct_idempotency_keys_distinct_jobs(
    db_session: AsyncSession,
) -> None:
    a = await enqueue(db_session, kind="t", idempotency_key="k1")
    b = await enqueue(db_session, kind="t", idempotency_key="k2")
    await db_session.commit()
    assert a != b


async def test_claim_one_transitions_to_running(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()

    claim = await claim_one(db_session, worker_id="w1", lease_secs=30)
    await db_session.commit()
    assert claim is not None
    assert claim.id == job_id
    assert claim.worker_id == "w1"
    assert claim.attempts == 1
    assert claim.cancel_requested is False

    await db_session.refresh(await db_session.get(Job, job_id))
    job = await db_session.get(Job, job_id)
    assert job.status == "running"
    assert job.locked_by == "w1"
    assert job.locked_at is not None
    assert job.lease_expires_at is not None
    assert job.heartbeat_at is not None


async def test_claim_one_returns_none_when_queue_empty(
    db_session: AsyncSession,
) -> None:
    assert await claim_one(db_session, worker_id="w1", lease_secs=30) is None


async def test_claim_one_filters_by_kind(db_session: AsyncSession) -> None:
    await enqueue(db_session, kind="profile_file")
    await enqueue(db_session, kind="execute_pipeline")
    await db_session.commit()

    claim = await claim_one(
        db_session, worker_id="w1", lease_secs=30, kinds=["execute_pipeline"]
    )
    assert claim is not None
    assert claim.kind == "execute_pipeline"


async def test_claim_one_skips_jobs_at_max_attempts(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=1)
    await db_session.commit()

    # First claim consumes the only attempt.
    c1 = await claim_one(db_session, worker_id="w1", lease_secs=30)
    assert c1 is not None
    # Manually requeue without claiming (simulate retryable-then-exhausted).
    job = await db_session.get(Job, job_id)
    job.status = "queued"
    job.locked_by = None
    job.lease_expires_at = None
    job.heartbeat_at = None
    await db_session.commit()

    # Now attempts (1) == max_attempts (1); claim_one should NOT pick it up.
    c2 = await claim_one(db_session, worker_id="w1", lease_secs=30)
    assert c2 is None


async def test_claim_one_concurrent_skip_locked(
    sessionmaker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """Two workers polling concurrently claim different jobs (FOR UPDATE SKIP LOCKED)."""
    await enqueue(db_session, kind="t")
    await enqueue(db_session, kind="t")
    await db_session.commit()

    async def claim_with_new_session(worker_id: str):
        async with sessionmaker() as s:
            c = await claim_one(s, worker_id=worker_id, lease_secs=30)
            await s.commit()
            return c

    a, b = await asyncio.gather(
        claim_with_new_session("worker-A"),
        claim_with_new_session("worker-B"),
    )
    assert a is not None
    assert b is not None
    assert a.id != b.id
    assert {a.worker_id, b.worker_id} == {"worker-A", "worker-B"}


async def test_heartbeat_extends_lease(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=5)
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    before = job.lease_expires_at
    await asyncio.sleep(0.01)

    still_owned, cancel_requested = await heartbeat(
        db_session, job_id, worker_id="w1", lease_secs=60
    )
    await db_session.commit()
    assert still_owned is True
    assert cancel_requested is False

    await db_session.refresh(job)
    assert job.lease_expires_at > before


async def test_heartbeat_returns_false_when_ownership_lost(
    db_session: AsyncSession,
) -> None:
    await enqueue(db_session, kind="t")
    await db_session.commit()
    claim = await claim_one(db_session, worker_id="w1", lease_secs=30)
    await db_session.commit()

    still_owned, _ = await heartbeat(
        db_session, claim.id, worker_id="other-worker", lease_secs=60
    )
    assert still_owned is False


async def test_heartbeat_surfaces_cancel_requested(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await request_cancel(db_session, job_id)
    await db_session.commit()

    still_owned, cancel_req = await heartbeat(
        db_session, job_id, worker_id="w1", lease_secs=60
    )
    assert still_owned is True
    assert cancel_req is True


async def test_fail_retryable_with_attempts_left_requeues(
    db_session: AsyncSession,
) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=3)
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await fail(
        db_session, job_id, worker_id="w1", error="oops", error_class="retryable"
    )
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "queued"
    assert job.locked_by is None
    assert job.lease_expires_at is None
    assert job.heartbeat_at is None
    assert job.last_error == "oops"
    assert job.error_class == "retryable"
    assert job.attempts == 1  # not decremented


async def test_fail_retryable_at_max_attempts_marks_failed(
    db_session: AsyncSession,
) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=1)
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await fail(
        db_session, job_id, worker_id="w1", error="oops", error_class="retryable"
    )
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "failed"
    assert job.finished_at is not None


async def test_fail_terminal_marks_failed_even_with_attempts_left(
    db_session: AsyncSession,
) -> None:
    job_id = await enqueue(db_session, kind="t", max_attempts=10)
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await fail(
        db_session, job_id, worker_id="w1", error="bad input", error_class="terminal"
    )
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "failed"
    assert job.error_class == "terminal"
    assert job.attempts == 1  # we burned only one attempt


async def test_fail_ignored_when_worker_mismatch(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await fail(
        db_session, job_id, worker_id="other", error="x", error_class="terminal"
    )
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "running"  # unchanged
    assert job.last_error is None


async def test_complete_marks_completed(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await complete(db_session, job_id, worker_id="w1")
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "completed"
    assert job.finished_at is not None
    assert job.last_error is None
    assert job.error_class is None


async def test_complete_gated_on_ownership(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await complete(db_session, job_id, worker_id="impostor")
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "running"


async def test_cancel_marks_cancelled(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await cancel(db_session, job_id)
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "cancelled"
    assert job.finished_at is not None


async def test_cancel_with_worker_id_gates_on_ownership(
    db_session: AsyncSession,
) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await claim_one(db_session, worker_id="w1", lease_secs=30)
    await cancel(db_session, job_id, worker_id="impostor")
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.status == "running"  # unchanged

    await cancel(db_session, job_id, worker_id="w1")
    await db_session.commit()
    job = await db_session.get(Job, job_id)
    assert job.status == "cancelled"


async def test_request_cancel_sets_flag(db_session: AsyncSession) -> None:
    job_id = await enqueue(db_session, kind="t")
    await db_session.commit()
    await request_cancel(db_session, job_id)
    await db_session.commit()

    job = await db_session.get(Job, job_id)
    assert job.cancel_requested is True
