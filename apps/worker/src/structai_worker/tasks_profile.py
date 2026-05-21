"""`profile_file` worker task (CHECKLIST.md line 108).

Driven by `structai_worker.tasks.dispatch` once `main.py` imports this
module (side-effect-only — the `@register("profile_file")` decorator
populates the global registry on import).

Idempotent on `(file_id, profile_version)`: if a `profiles` row already
exists for this file id, the task no-ops. The queue's idempotency-key
mechanism (set by the API at enqueue time) usually prevents a re-run,
but this catches the re-run-on-retry case too.

Two-artifact output (plan §13):
  - `profiles.profile_jsonb` ← redacted (LLM-safe)
  - `./data/profiles/<profile_sha256>.raw.json` ← raw (local only)
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.config import Settings
from structai_core.db.models import File, Profile
from structai_core.io.sniff import SniffError, sniff
from structai_core.jobs import CancellationToken, RetryableError, TerminalError
from structai_core.profile.runner import profile_file as run_profile

from structai_worker.tasks import register

log = logging.getLogger(__name__)


@register("profile_file")
async def profile_file_task(
    session: AsyncSession,
    payload: dict[str, Any],
    token: CancellationToken,
) -> None:
    file_id = payload.get("file_id")
    profile_version = payload.get("profile_version", "v1")
    if not isinstance(file_id, int):
        raise TerminalError(f"profile_file payload missing file_id: {payload!r}")

    file = (
        await session.execute(select(File).where(File.id == file_id))
    ).scalar_one_or_none()
    if file is None:
        raise TerminalError(f"file id {file_id} not found")

    if await _profile_exists(session, file_id):
        log.info("profile already exists for file_id=%d; no-op", file_id)
        return

    if file.live_path is None:
        raise TerminalError(f"file id {file_id} has no live_path")
    live_path = Path(file.live_path)
    if not live_path.exists():
        raise TerminalError(f"live file missing: {live_path}")

    settings = Settings()
    try:
        sniff_result = await asyncio.to_thread(sniff, live_path)
    except SniffError as exc:
        raise TerminalError(f"sniff failed: {exc}") from exc

    profile_result = await run_profile(
        live_path,
        sniff=sniff_result,
        source_sha256=file.source_sha256,
        profile_version=profile_version,
        token=token,
        settings=settings,
    )

    profile_sha = profile_result.redacted.profile_sha256
    try:
        await asyncio.to_thread(
            _write_raw_artifact,
            settings.data_dir,
            profile_sha,
            profile_result.raw.model_dump(mode="json"),
        )
    except OSError as exc:
        raise RetryableError(f"raw artifact write failed: {exc}") from exc

    session.add(
        Profile(
            file_id=file.id,
            profile_sha256=profile_sha,
            profile_jsonb=profile_result.redacted.model_dump(mode="json"),
        )
    )
    await session.commit()
    log.info("profile_file complete file_id=%d profile_sha=%s", file_id, profile_sha[:8])


async def _profile_exists(session: AsyncSession, file_id: int) -> bool:
    row = (
        await session.execute(
            text("SELECT 1 FROM profiles WHERE file_id = :fid LIMIT 1"),
            {"fid": file_id},
        )
    ).first()
    return row is not None


def _write_raw_artifact(data_dir: Path, profile_sha: str, raw: dict[str, Any]) -> None:
    out_dir = data_dir / "profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{profile_sha}.raw.json"
    path.write_text(json.dumps(raw, sort_keys=True))
