"""End-to-end cancellation integration test (CHECKLIST.md line 143).

Enqueues a real `profile_file` job pointing at a generated wide CSV,
drives `_process_one` (the worker's lifecycle wrapper for one job),
sends `request_cancel` while profiling is in flight, and asserts:

  * the job lands in `cancelled` (not `completed`, not `failed`)
  * no `profiles` row was inserted

This is informational with respect to Phase 0 (which was already closed
by `tests/worker/test_main_loop.py::test_cooperative_cancel_during_run`),
but adds the realistic-task variant — a Polars-driven multi-column
profile rather than a synthetic `sleep` loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from structai_core.config import Settings
from structai_core.db.models import File, Job
from structai_core.jobs.queue import claim_one, enqueue, request_cancel

# Importing tasks_profile registers @register("profile_file").
from structai_worker import tasks_profile  # noqa: F401
from structai_worker.main import _process_one


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("STRUCTAI_DATA_DIR", str(tmp_path / "data"))
    s = Settings()
    s.worker_heartbeat_secs = 0  # heartbeat as tight as the event loop allows
    s.worker_lease_secs = 60
    return s


def _generate_wide_csv(path: Path, *, cols: int = 60, rows: int = 5000) -> None:
    """Write a wide CSV with mixed column shapes so per-column compute
    has real work to do (regex matches, top-K, quantiles, PK score)."""
    header = ",".join([f"col_{i:03d}" for i in range(cols)])
    lines = [header]
    for r in range(rows):
        cells = []
        for c in range(cols):
            shape = c % 4
            if shape == 0:
                cells.append(str(r * 7 + c))                        # int
            elif shape == 1:
                cells.append(f"{(r + c) * 1.37:.2f}")               # float
            elif shape == 2:
                cells.append(f"user_{r % 100:04d}_label_{c}")       # string
            else:
                cells.append(f"alice{r}_{c}@example.com")           # email
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n")


async def _stage_file(
    db_session: AsyncSession, settings: Settings
) -> File:
    live_dir = settings.data_dir / "uploads" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    src = live_dir / "tmp_wide.csv"
    _generate_wide_csv(src)
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    live_path = live_dir / f"{sha}.csv"
    shutil.move(src, live_path)

    file = File(
        original_name="wide.csv",
        bytes=live_path.stat().st_size,
        source_sha256=sha,
        quarantine_path=None,
        live_path=str(live_path),
    )
    db_session.add(file)
    await db_session.commit()
    await db_session.refresh(file)
    return file


async def _claim(sessionmaker: async_sessionmaker[AsyncSession]):
    async with sessionmaker() as s:
        c = await claim_one(s, worker_id="w-cancel-test", lease_secs=60)
        await s.commit()
        return c


async def test_profile_file_cancels_mid_run(
    db_session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    file = await _stage_file(db_session, settings)
    await enqueue(
        db_session,
        kind="profile_file",
        payload={"file_id": file.id, "profile_version": "v1"},
        idempotency_key=f"profile_file:{file.source_sha256}:v1",
    )
    await db_session.commit()

    claim = await _claim(sessionmaker)
    assert claim is not None
    assert claim.kind == "profile_file"

    process = asyncio.create_task(
        _process_one(sessionmaker, claim, settings),
        name="process_one",
    )

    # Give profile_column a chance to start; then yank the brake.
    await asyncio.sleep(0.05)
    async with sessionmaker() as s:
        await request_cancel(s, claim.id)
        await s.commit()

    await asyncio.wait_for(process, timeout=15.0)

    async with sessionmaker() as s:
        job = await s.get(Job, claim.id)
        assert job.status == "cancelled", f"got status={job.status}"

    # No profiles row should have been inserted (the task commits as the
    # last step; cancellation should fire before that).
    n = (
        await db_session.execute(
            text("SELECT count(*) FROM profiles WHERE file_id = :fid"),
            {"fid": file.id},
        )
    ).scalar()
    assert n == 0
