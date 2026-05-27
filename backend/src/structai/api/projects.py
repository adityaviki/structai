from __future__ import annotations

import asyncpg
from fastapi import APIRouter

from ..db.ids import new_id, project_db_name, slugify
from ..db.pool import connect_admin
from ..db.pools import get_pools
from ..logging import log
from ..schemas.project import ProjectIn, ProjectOut, ProjectStats, ProjectWithStatsOut
from ..settings import get_settings
from .errors import ApiError

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _row_to_project(row: asyncpg.Record) -> ProjectOut:
    return ProjectOut(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        emoji=row["emoji"],
        color=row["color"],
        db_name=row["db_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def _create_project_db(db_name: str) -> None:
    settings = get_settings()
    admin = await connect_admin(settings)
    try:
        # Quote the identifier to defend against weird slugs; db_name is
        # already constructed from a slugified input but defense-in-depth.
        await admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin.close()


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn) -> ProjectOut:
    pools = get_pools()
    meta = await pools.meta()

    project_id = new_id()
    slug = slugify(body.name)
    db_name = project_db_name(slug, project_id)

    try:
        await _create_project_db(db_name)
    except asyncpg.DuplicateDatabaseError as exc:
        raise ApiError(
            status=409,
            title="Project DB collision",
            detail=f"Database {db_name!r} already exists.",
        ) from exc

    try:
        async with meta.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO projects (id, name, description, emoji, color, db_name)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, name, description, emoji, color, db_name, created_at, updated_at
                """,
                project_id,
                body.name,
                body.description,
                body.emoji,
                body.color,
                db_name,
            )
    except Exception:
        # Roll back the per-project DB we just created so we don't leak it.
        try:
            settings = get_settings()
            admin = await connect_admin(settings)
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            finally:
                await admin.close()
        except Exception:
            log.exception("project.create.rollback_failed", db_name=db_name)
        raise

    assert row is not None
    log.info("project.created", id=project_id, db_name=db_name)
    return _row_to_project(row)


@router.get("", response_model=list[ProjectWithStatsOut])
async def list_projects() -> list[ProjectWithStatsOut]:
    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.*,
                COALESCE(d.cnt, 0) AS docs_count,
                COALESCE(r.cnt, 0) AS completed_imports
            FROM projects p
            LEFT JOIN (
                SELECT project_id, COUNT(*)::int AS cnt
                FROM documents GROUP BY project_id
            ) d ON d.project_id = p.id
            LEFT JOIN (
                SELECT project_id, COUNT(*)::int AS cnt
                FROM import_runs
                WHERE status = 'completed'
                GROUP BY project_id
            ) r ON r.project_id = p.id
            ORDER BY p.updated_at DESC
            """
        )
    return [
        ProjectWithStatsOut(
            **_row_to_project(row).model_dump(),
            stats=ProjectStats(
                tables=0,  # Phase 1: filled in by a separate /tables endpoint.
                documents=row["docs_count"],
                imports_completed=row["completed_imports"],
            ),
        )
        for row in rows
    ]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str) -> ProjectOut:
    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1",
            project_id,
        )
    if row is None:
        raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")
    return _row_to_project(row)
