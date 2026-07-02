"""Data-access layer for the chat agent: messages + proposed/applied changes.

Concentrates the chat SQL here, mirroring ``runs_repo`` for import runs.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .pools import get_pools

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    import asyncpg


async def get_project_db(project_id: str) -> str | None:
    """Return the project's Postgres DB name, or None if the project is gone."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        db_name = await conn.fetchval("SELECT db_name FROM projects WHERE id = $1", project_id)
    return None if db_name is None else str(db_name)


async def insert_message(
    *,
    message_id: str,
    project_id: str,
    role: str,
    content: str,
    change_id: str | None = None,
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_messages (id, project_id, role, content, change_id)
            VALUES ($1, $2, $3, $4, $5)
            """,
            message_id,
            project_id,
            role,
            content,
            change_id,
        )


async def get_message(message_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM chat_messages WHERE id = $1", message_id)


async def list_messages(project_id: str) -> list[asyncpg.Record]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            "SELECT * FROM chat_messages WHERE project_id = $1 ORDER BY created_at ASC, id ASC",
            project_id,
        )
        return rows


async def insert_change(
    *,
    change_id: str,
    project_id: str,
    target_table: str | None,
    summary: str | None,
    sql: str,
    affected_rows: int | None,
    total_rows: int | None,
    preview: list[dict[str, str]] | None,
) -> None:
    meta = await get_pools().meta()
    preview_json = json.dumps(preview) if preview is not None else None
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO data_changes
                (id, project_id, target_table, summary, sql, affected_rows,
                 total_rows, preview)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            change_id,
            project_id,
            target_table,
            summary,
            sql,
            affected_rows,
            total_rows,
            preview_json,
        )


async def get_change(change_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM data_changes WHERE id = $1", change_id)


async def get_changes(change_ids: Sequence[str]) -> list[asyncpg.Record]:
    if not change_ids:
        return []
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            "SELECT * FROM data_changes WHERE id = ANY($1::text[])",
            list(change_ids),
        )
        return rows


async def change_holding_snapshot(project_id: str) -> asyncpg.Record | None:
    """The change that currently owns the project's undo snapshot, if any.

    At most one row per project has a non-null ``snapshot_db`` (we drop the
    prior one each time a new change is applied), so this is the rollback point.
    """

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT * FROM data_changes
            WHERE project_id = $1 AND snapshot_db IS NOT NULL
            ORDER BY applied_at DESC NULLS LAST
            LIMIT 1
            """,
            project_id,
        )


async def set_change_status(
    *,
    change_id: str,
    status: str | None = None,
    snapshot_db: str | None = None,
    clear_snapshot: bool = False,
    applied_at: datetime | None = None,
    reverted_at: datetime | None = None,
    affected_rows: int | None = None,
    total_rows: int | None = None,
) -> None:
    sets: list[str] = []
    args: list[Any] = [change_id]
    i = 2
    if status is not None:
        sets.append(f"status = ${i}")
        args.append(status)
        i += 1
    if snapshot_db is not None:
        sets.append(f"snapshot_db = ${i}")
        args.append(snapshot_db)
        i += 1
    if clear_snapshot:
        sets.append("snapshot_db = NULL")
    if applied_at is not None:
        sets.append(f"applied_at = ${i}")
        args.append(applied_at)
        i += 1
    if reverted_at is not None:
        sets.append(f"reverted_at = ${i}")
        args.append(reverted_at)
        i += 1
    if affected_rows is not None:
        sets.append(f"affected_rows = ${i}")
        args.append(affected_rows)
        i += 1
    if total_rows is not None:
        sets.append(f"total_rows = ${i}")
        args.append(total_rows)
        i += 1
    if not sets:
        return
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            f"UPDATE data_changes SET {', '.join(sets)} WHERE id = $1",
            *args,
        )
