"""Data access for schema proposals.

A schema proposal is the agent's draft DDL that the user must accept (or
ask to be revised) before the import script is generated. Each revision
creates a new row with iteration = previous + 1; the previous row is
flipped to ``superseded``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .pools import get_pools

if TYPE_CHECKING:
    import asyncpg


async def create_proposal(
    *,
    proposal_id: str,
    run_id: str,
    iteration: int,
    schema_ddl: str,
    tables: list[str],
    rationale: str,
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO schema_proposals
                (id, run_id, iteration, schema_ddl, tables, rationale)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            proposal_id,
            run_id,
            iteration,
            schema_ddl,
            tables,
            rationale,
        )


async def get_proposal(proposal_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM schema_proposals WHERE id = $1", proposal_id
        )


async def list_for_run(run_id: str) -> list[asyncpg.Record]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            "SELECT * FROM schema_proposals WHERE run_id = $1 ORDER BY iteration ASC",
            run_id,
        )
    return rows


async def latest_for_run(run_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM schema_proposals
            WHERE run_id = $1
            ORDER BY iteration DESC
            LIMIT 1
            """,
            run_id,
        )


async def is_decided(proposal_id: str) -> bool:
    """True if status moved off 'pending' (accepted or superseded)."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        val = await conn.fetchval(
            "SELECT status FROM schema_proposals WHERE id = $1", proposal_id
        )
    return val is not None and val != "pending"


async def accept(
    *,
    proposal_id: str,
    auto: bool = False,
) -> bool:
    """Mark a proposal accepted. Returns True if a pending row was updated."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE schema_proposals
            SET status = 'accepted',
                auto_accepted = $2,
                decided_at = $3
            WHERE id = $1 AND status = 'pending'
            """,
            proposal_id,
            auto,
            datetime.now(UTC),
        )
    return bool(result.split()[1] != "0")


async def supersede_with_feedback(
    *,
    proposal_id: str,
    feedback: str,
) -> bool:
    """Mark a proposal superseded and record the user's revision request."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE schema_proposals
            SET status = 'superseded',
                feedback = $2,
                decided_at = $3
            WHERE id = $1 AND status = 'pending'
            """,
            proposal_id,
            feedback,
            datetime.now(UTC),
        )
    return bool(result.split()[1] != "0")
