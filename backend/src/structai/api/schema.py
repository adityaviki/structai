"""Schema-diagram endpoints: introspection + layout persistence (Phase 5)."""

from __future__ import annotations

from fastapi import APIRouter

from ..db.pools import get_pools
from ..schemas.schema_diagram import (
    FkRef,
    LayoutOut,
    LayoutPosition,
    LayoutUpsertIn,
    ProjectSchemaOut,
    SchemaColumn,
    SchemaTable,
)
from .errors import ApiError

router = APIRouter(prefix="/api/projects/{project_id}/schema", tags=["schema"])


async def _resolve_project_db(project_id: str) -> str:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        db_name = await conn.fetchval(
            "SELECT db_name FROM projects WHERE id = $1", project_id
        )
    if db_name is None:
        raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")
    assert isinstance(db_name, str)
    return db_name


@router.get("", response_model=ProjectSchemaOut)
async def get_schema(project_id: str) -> ProjectSchemaOut:
    db_name = await _resolve_project_db(project_id)
    pool = await get_pools().project(db_name)

    async with pool.acquire() as conn:
        # Tables in `public`.
        table_rows = await conn.fetch(
            """
            SELECT c.relname AS name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY c.relname
            """
        )

        # All columns for those tables.
        col_rows = await conn.fetch(
            """
            SELECT table_name, column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )

        # PKs.
        pk_rows = await conn.fetch(
            """
            SELECT c.relname AS table_name, a.attname AS column_name
            FROM   pg_index i
            JOIN   pg_class c ON c.oid = i.indrelid
            JOIN   pg_namespace n ON n.oid = c.relnamespace
            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE  n.nspname = 'public' AND i.indisprimary
            """
        )
        pks: dict[str, set[str]] = {}
        for r in pk_rows:
            pks.setdefault(r["table_name"], set()).add(r["column_name"])

        # FKs.
        fk_rows = await conn.fetch(
            """
            SELECT tc.table_name AS src_table,
                   kcu.column_name AS src_column,
                   ccu.table_name AS dst_table,
                   ccu.column_name AS dst_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
               AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )
        fks: dict[tuple[str, str], FkRef] = {}
        for r in fk_rows:
            fks[(r["src_table"], r["src_column"])] = FkRef(
                table=r["dst_table"], column=r["dst_column"]
            )

        # Row counts. Each call is its own query — fine at our scale.
        row_counts: dict[str, int] = {}
        for tr in table_rows:
            n = await conn.fetchval(f'SELECT COUNT(*) FROM "{tr["name"]}"')
            row_counts[tr["name"]] = int(n or 0)

    by_table: dict[str, list[SchemaColumn]] = {}
    for cr in col_rows:
        by_table.setdefault(cr["table_name"], []).append(
            SchemaColumn(
                name=cr["column_name"],
                type=cr["data_type"],
                nullable=(cr["is_nullable"] == "YES"),
                is_pk=cr["column_name"] in pks.get(cr["table_name"], set()),
                fk=fks.get((cr["table_name"], cr["column_name"])),
            )
        )

    tables = [
        SchemaTable(
            name=tr["name"],
            columns=by_table.get(tr["name"], []),
            row_count=row_counts.get(tr["name"], 0),
        )
        for tr in table_rows
    ]
    return ProjectSchemaOut(tables=tables)


@router.get("/layout", response_model=LayoutOut)
async def get_layout(project_id: str) -> LayoutOut:
    await _resolve_project_db(project_id)  # 404 on unknown project
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name, x, y FROM schema_layouts WHERE project_id = $1",
            project_id,
        )
    return LayoutOut(
        positions=[
            LayoutPosition(table_name=r["table_name"], x=r["x"], y=r["y"]) for r in rows
        ]
    )


@router.post("/layout", response_model=LayoutOut)
async def upsert_layout(project_id: str, body: LayoutUpsertIn) -> LayoutOut:
    await _resolve_project_db(project_id)
    meta = await get_pools().meta()
    async with meta.acquire() as conn, conn.transaction():
        for p in body.positions:
            await conn.execute(
                """
                INSERT INTO schema_layouts (project_id, table_name, x, y)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (project_id, table_name) DO UPDATE
                SET x = EXCLUDED.x, y = EXCLUDED.y, updated_at = now()
                """,
                project_id,
                p.table_name,
                p.x,
                p.y,
            )
    return await get_layout(project_id)
