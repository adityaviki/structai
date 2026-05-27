"""Data-access layer for import runs and pipeline steps.

We keep DB access concentrated here so the orchestrator and API code don't
sprinkle SQL throughout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .pools import get_pools

if TYPE_CHECKING:
    from datetime import datetime

    import asyncpg


async def get_run(run_id: str) -> asyncpg.Record | None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT r.*, d.name AS document_name, d.storage_path AS document_storage_path,
                   d.ext AS document_ext, p.db_name AS project_db_name,
                   p.model_override AS project_model_override
            FROM import_runs r
            JOIN documents d ON d.id = r.document_id
            JOIN projects  p ON p.id = r.project_id
            WHERE r.id = $1
            """,
            run_id,
        )


async def list_run_steps(run_id: str) -> list[asyncpg.Record]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            """
            SELECT * FROM pipeline_steps
            WHERE run_id = $1
            ORDER BY id ASC
            """,
            run_id,
        )
        return rows


async def list_project_runs(project_id: str) -> list[asyncpg.Record]:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows: list[asyncpg.Record] = await conn.fetch(
            "SELECT * FROM import_runs WHERE project_id = $1 ORDER BY started_at DESC",
            project_id,
        )
        return rows


async def create_run(
    *,
    run_id: str,
    project_id: str,
    document_id: str,
    title: str,
    instructions: str | None,
    auto_mode: bool,
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO import_runs (id, project_id, document_id, title, instructions, auto_mode)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            run_id,
            project_id,
            document_id,
            title,
            instructions,
            auto_mode,
        )


async def set_run_status(
    *,
    run_id: str,
    status: str,
    progress: int | None = None,
    error_message: str | None = None,
    rows_imported: int | None = None,
    total_rows: int | None = None,
    created_tables: list[str] | None = None,
    finished_at: datetime | None = None,
    snapshot_db: str | None = None,
    reverted_at: datetime | None = None,
    reverted_by_run_id: str | None = None,
    clear_snapshot: bool = False,
) -> None:
    meta = await get_pools().meta()
    sets: list[str] = ["status = $2"]
    args: list[Any] = [run_id, status]
    i = 3
    if progress is not None:
        sets.append(f"progress = ${i}")
        args.append(progress)
        i += 1
    if error_message is not None:
        sets.append(f"error_message = ${i}")
        args.append(error_message)
        i += 1
    if rows_imported is not None:
        sets.append(f"rows_imported = ${i}")
        args.append(rows_imported)
        i += 1
    if total_rows is not None:
        sets.append(f"total_rows = ${i}")
        args.append(total_rows)
        i += 1
    if created_tables is not None:
        sets.append(f"created_tables = ${i}")
        args.append(created_tables)
        i += 1
    if finished_at is not None:
        sets.append(f"finished_at = ${i}")
        args.append(finished_at)
        i += 1
    if snapshot_db is not None:
        sets.append(f"snapshot_db = ${i}")
        args.append(snapshot_db)
        i += 1
    if clear_snapshot:
        sets.append("snapshot_db = NULL")
    if reverted_at is not None:
        sets.append(f"reverted_at = ${i}")
        args.append(reverted_at)
        i += 1
    if reverted_by_run_id is not None:
        sets.append(f"reverted_by_run_id = ${i}")
        args.append(reverted_by_run_id)
        i += 1

    async with meta.acquire() as conn:
        await conn.execute(
            f"UPDATE import_runs SET {', '.join(sets)} WHERE id = $1",
            *args,
        )


async def cancel_requested(run_id: str) -> bool:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        val = await conn.fetchval(
            "SELECT cancel_requested FROM import_runs WHERE id = $1", run_id
        )
    return bool(val)


async def request_cancel(run_id: str) -> bool:
    """Set cancel_requested = true. Returns True if the row was updated."""

    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        result = await conn.execute(
            "UPDATE import_runs SET cancel_requested = true "
            "WHERE id = $1 AND status NOT IN ('completed','failed','cancelled','reverted')",
            run_id,
        )
    # asyncpg returns "UPDATE n" — split and parse.
    parts = result.split()
    return bool(parts[0] == "UPDATE" and parts[1] != "0")


async def upsert_step(
    *,
    run_id: str,
    step_key: str,
    status: str,
    title: str,
    summary: str | None = None,
    code: str | None = None,
    language: str | None = None,
    attempts: int = 1,
    errors: list[str] | None = None,
    started_at: datetime | None = None,
    duration_ms: int | None = None,
) -> None:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pipeline_steps
                (run_id, step_key, status, title, summary, code, language,
                 attempts, errors, started_at, duration_ms)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (run_id, step_key, attempts) DO UPDATE
            SET status = EXCLUDED.status,
                summary = EXCLUDED.summary,
                code = EXCLUDED.code,
                language = EXCLUDED.language,
                errors = EXCLUDED.errors,
                started_at = COALESCE(pipeline_steps.started_at, EXCLUDED.started_at),
                duration_ms = EXCLUDED.duration_ms
            """,
            run_id,
            step_key,
            status,
            title,
            summary,
            code,
            language,
            attempts,
            errors,
            started_at,
            duration_ms,
        )
