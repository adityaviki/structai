"""Snapshot retention sweeper (D15) + worker restart recovery.

Runs as an arq cron job. For each project, keeps the most recent
``KEEP_LAST_N`` snapshots; drops older ones and clears their
``snapshot_db`` pointers so the UI knows their undo isn't available
anymore.
"""

from __future__ import annotations

from typing import Any

from ..db import settings_repo
from ..db.pools import get_pools
from ..db.snapshots import drop_snapshot
from ..logging import log
from ..settings import get_settings

ACTIVE_STATUSES = (
    "profiling",
    "generating",
    "executing",
    "fixing",
    "validating",
    "cancelling",
    "needs_clarification",
    "awaiting_schema_approval",
)


async def sweep_snapshots(_ctx: dict[str, Any]) -> int:
    """Drop snapshots beyond the retention window. Returns count dropped."""

    settings = get_settings()
    keep_last_n, max_age_days = await settings_repo.effective_retention()
    meta = await get_pools().meta()
    dropped = 0
    async with meta.acquire() as conn:
        # Drop by retention count.
        rows = await conn.fetch(
            """
            WITH ranked AS (
                SELECT id, snapshot_db,
                       row_number() OVER (
                           PARTITION BY project_id
                           ORDER BY finished_at DESC NULLS LAST, started_at DESC
                       ) AS rk
                FROM import_runs
                WHERE snapshot_db IS NOT NULL
                  AND snapshot_pinned = false
                  AND status = 'completed'
            )
            SELECT id, snapshot_db FROM ranked WHERE rk > $1
            """,
            keep_last_n,
        )
        for r in rows:
            try:
                await drop_snapshot(settings=settings, snapshot_db=r["snapshot_db"])
            except Exception:  # noqa: BLE001
                log.exception("sweeper.drop_failed", snapshot_db=r["snapshot_db"])
                continue
            await conn.execute(
                "UPDATE import_runs SET snapshot_db = NULL WHERE id = $1", r["id"]
            )
            dropped += 1

        # Drop by max age (only if positive).
        if max_age_days > 0:
            old_rows = await conn.fetch(
                """
                SELECT id, snapshot_db
                FROM import_runs
                WHERE snapshot_db IS NOT NULL
                  AND snapshot_pinned = false
                  AND status = 'completed'
                  AND finished_at < now() - ($1::int * interval '1 day')
                """,
                max_age_days,
            )
            for r in old_rows:
                try:
                    await drop_snapshot(settings=settings, snapshot_db=r["snapshot_db"])
                except Exception:  # noqa: BLE001
                    log.exception("sweeper.age_drop_failed", snapshot_db=r["snapshot_db"])
                    continue
                await conn.execute(
                    "UPDATE import_runs SET snapshot_db = NULL WHERE id = $1", r["id"]
                )
                dropped += 1
    if dropped:
        log.info("sweeper.done", dropped=dropped)
    return dropped


async def recover_interrupted_runs(_ctx: dict[str, Any]) -> int:
    """Mark stranded active-status runs as failed/cancelled on startup.

    Called once when the worker boots. Any run sitting in an active status
    can't actually be running (we just started); it's leftover state from a
    crashed or restarted worker. We:

      1. Cancel-requested rows → status='cancelled'
      2. Everything else      → status='failed'
      3. Drop any snapshot the row was holding.
    """

    settings = get_settings()
    meta = await get_pools().meta()
    cleaned = 0
    async with meta.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, snapshot_db, cancel_requested
            FROM import_runs
            WHERE status IN ({','.join(f"'{s}'" for s in ACTIVE_STATUSES)})
            """
        )
        for r in rows:
            new_status = "cancelled" if r["cancel_requested"] else "failed"
            await conn.execute(
                """
                UPDATE import_runs
                SET status = $2,
                    finished_at = COALESCE(finished_at, now()),
                    error_message = COALESCE(error_message, $3),
                    snapshot_db = NULL
                WHERE id = $1
                """,
                r["id"],
                new_status,
                "Interrupted by worker restart.",
            )
            if r["snapshot_db"]:
                try:
                    await drop_snapshot(settings=settings, snapshot_db=r["snapshot_db"])
                except Exception:  # noqa: BLE001
                    log.exception("recover.snapshot_drop_failed", snapshot_db=r["snapshot_db"])
            cleaned += 1
    if cleaned:
        log.info("recover.cleaned", cleaned=cleaned)
    return cleaned
