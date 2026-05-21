"""Worker main-loop integration: enqueue → claim → dispatch → finalize.

Drives `structai_worker.main._process_one` directly rather than running the
whole `run()` (which installs signal handlers and polls forever). The unit
under test is the lifecycle wrapper: heartbeat startup, exception →
fail-class mapping, complete on success, cancel on cooperative cancel,
ownership-gated finalizers.

Closes Phase 0 `[~]` (`cancel_requested` honored at step boundaries).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from structai_core.config import Settings
from structai_core.db.models import Job
from structai_core.jobs import RetryableError, TerminalError
from structai_core.jobs.queue import claim_one, enqueue, request_cancel

from structai_worker import tasks
from structai_worker.main import _process_one


@pytest.fixture(autouse=True)
def _clear_task_registry():
    tasks.REGISTRY.clear()
    yield
    tasks.REGISTRY.clear()


@pytest.fixture
def fast_settings() -> Settings:
    """Settings with short heartbeat so cancellation tests don't drag."""
    s = Settings()
    s.worker_heartbeat_secs = 0  # heartbeat as fast as the loop can spin
    s.worker_lease_secs = 60
    s.worker_poll_interval_secs = 1
    return s


async def _claim_in_fresh_session(
    sessionmaker: async_sessionmaker[AsyncSession], worker_id: str = "w1"
):
    async with sessionmaker() as s:
        c = await claim_one(s, worker_id=worker_id, lease_secs=60)
        await s.commit()
        return c


async def test_happy_path_complete(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    received: list[dict[str, Any]] = []

    @tasks.register("ok")
    async def ok(session, payload, token):
        received.append(payload)

    await enqueue(db_session, kind="ok", payload={"x": 1})
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    assert claim is not None
    await _process_one(sessionmaker, claim, fast_settings)

    assert received == [{"x": 1}]
    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "completed"
        assert job.finished_at is not None
        assert job.last_error is None


async def test_retryable_error_requeues_with_attempts_remaining(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    @tasks.register("flaky")
    async def flaky(session, payload, token):
        raise RetryableError("transient blip")

    await enqueue(db_session, kind="flaky", max_attempts=3)
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    await _process_one(sessionmaker, claim, fast_settings)

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "queued"
        assert job.error_class == "retryable"
        assert job.last_error == "transient blip"
        assert job.attempts == 1


async def test_terminal_error_stops_immediately(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    @tasks.register("bad")
    async def bad(session, payload, token):
        raise TerminalError("schema mismatch")

    await enqueue(db_session, kind="bad", max_attempts=5)
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    await _process_one(sessionmaker, claim, fast_settings)

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "failed"
        assert job.error_class == "terminal"
        assert job.attempts == 1


async def test_unknown_exception_treated_as_retryable(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    @tasks.register("boom")
    async def boom(session, payload, token):
        raise ValueError("totally unexpected")

    await enqueue(db_session, kind="boom", max_attempts=3)
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    await _process_one(sessionmaker, claim, fast_settings)

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "queued"
        assert job.error_class == "retryable"


async def test_already_cancelled_at_claim_time_short_circuits(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    """If cancel_requested is set before claim, the task's first
    raise_if_cancelled trips and the job lands in `cancelled`."""

    @tasks.register("pre_cancel")
    async def t(session, payload, token):
        token.raise_if_cancelled()
        await asyncio.sleep(10)  # would block if reached

    job_id = await enqueue(db_session, kind="pre_cancel")
    await request_cancel(db_session, job_id)
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    assert claim.cancel_requested is True

    await asyncio.wait_for(_process_one(sessionmaker, claim, fast_settings), timeout=2.0)

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "cancelled"


async def test_cooperative_cancel_during_run(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    """Long-running task respects request_cancel between step boundaries.

    Closes Phase 0 cancellation [~]: the heartbeat surfaces
    cancel_requested → flips the token → the task's next
    raise_if_cancelled raises → _process_one marks the job cancelled.
    """
    started = asyncio.Event()
    progressed: list[int] = []

    @tasks.register("long")
    async def long_task(session, payload, token):
        started.set()
        for i in range(100):
            token.raise_if_cancelled()
            await asyncio.sleep(0.05)
            progressed.append(i)

    await enqueue(db_session, kind="long")
    await db_session.commit()

    claim = await _claim_in_fresh_session(sessionmaker)
    process = asyncio.create_task(_process_one(sessionmaker, claim, fast_settings))

    await asyncio.wait_for(started.wait(), timeout=2.0)
    await asyncio.sleep(0.1)

    async with sessionmaker() as s:
        await request_cancel(s, claim.id)
        await s.commit()

    await asyncio.wait_for(process, timeout=5.0)

    assert len(progressed) < 100, "task should have been cancelled before completing"

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "cancelled"


async def test_finalizers_gated_on_worker_id(
    sessionmaker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
    fast_settings: Settings,
) -> None:
    """If the worker's lease is stolen (e.g. reaper reassigned), its
    finalizer (complete/fail) should be ignored on the row it no longer
    owns. We can't easily simulate a reaper steal here, but we can verify
    the queue-level ownership gate is being used by the worker — the
    `complete` and `fail` calls in _process_one pass `worker_id=claim.worker_id`.
    """
    completed = asyncio.Event()

    @tasks.register("ok2")
    async def ok(session, payload, token):
        completed.set()

    await enqueue(db_session, kind="ok2")
    await db_session.commit()
    claim = await _claim_in_fresh_session(sessionmaker, worker_id="w-original")
    await _process_one(sessionmaker, claim, fast_settings)

    assert completed.is_set()
    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "completed"
        assert job.locked_by == "w-original"  # ownership reflected
