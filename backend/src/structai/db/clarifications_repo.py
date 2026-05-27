"""Data access for clarifications."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .pools import get_pools

if TYPE_CHECKING:
    import asyncpg


async def create_clarification(
    *,
    clar_id: str,
    run_id: str,
    question: str,
    context: str | None,
    options: list[dict[str, Any]],
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clarifications (id, run_id, question, context, options)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            clar_id,
            run_id,
            question,
            context,
            json.dumps(options),
        )


async def record_auto_decision(
    *,
    clar_id: str,
    choice_id: str,
    reasoning: str,
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            UPDATE clarifications
            SET answer_choice_id = $2,
                auto_decision = true,
                auto_reasoning = $3,
                answered_at = $4
            WHERE id = $1
            """,
            clar_id,
            choice_id,
            reasoning,
            datetime.now(UTC),
        )


async def record_user_answer(
    *,
    clar_id: str,
    choice_id: str | None,
    custom: str | None,
) -> bool:
    """Set the answer if not already set. Returns True if a row was updated."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE clarifications
            SET answer_choice_id = $2,
                answer_custom = $3,
                answered_at = $4
            WHERE id = $1 AND answered_at IS NULL
            """,
            clar_id,
            choice_id,
            custom,
            datetime.now(UTC),
        )
    return bool(result.split()[1] != "0")


async def get_clarification(clar_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM clarifications WHERE id = $1", clar_id)


async def list_for_run(run_id: str) -> list[asyncpg.Record]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            "SELECT * FROM clarifications WHERE run_id = $1 ORDER BY created_at ASC",
            run_id,
        )
        return rows


async def is_answered(clar_id: str) -> bool:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        val = await conn.fetchval(
            "SELECT answered_at IS NOT NULL FROM clarifications WHERE id = $1", clar_id
        )
    return bool(val)
