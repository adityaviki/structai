"""Data tab API: list tables in the project DB and paginate rows."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Query

from ..db.pools import get_pools
from ..schemas.table import ColumnOut, FkRef, RowsPage, TableDetail, TableSummary
from .errors import ApiError

router = APIRouter(prefix="/api/projects/{project_id}", tags=["tables"])


async def _resolve_project_db(project_id: str) -> str:
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        db_name = await conn.fetchval("SELECT db_name FROM projects WHERE id = $1", project_id)
    if db_name is None:
        raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")
    assert isinstance(db_name, str)
    return db_name


@router.get("/tables", response_model=list[TableSummary])
async def list_tables(project_id: str) -> list[TableSummary]:
    db_name = await _resolve_project_db(project_id)
    pool = await get_pools().project(db_name)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.relname AS name,
                   c.reltuples::bigint AS row_estimate,
                   (SELECT COUNT(*) FROM information_schema.columns
                      WHERE table_schema = 'public' AND table_name = c.relname) AS column_count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY c.relname
            """
        )
        # Get exact row counts (small tables — fine in dev/local).
        out: list[TableSummary] = []
        for r in rows:
            exact = await conn.fetchval(f'SELECT COUNT(*) FROM "{r["name"]}"')
            out.append(
                TableSummary(
                    name=r["name"],
                    row_count=int(exact or 0),
                    column_count=int(r["column_count"]),
                )
            )
    return out


@router.get("/tables/{table_name}", response_model=TableDetail)
async def get_table(project_id: str, table_name: str) -> TableDetail:
    db_name = await _resolve_project_db(project_id)
    pool = await get_pools().project(db_name)
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1",
            table_name,
        )
        if exists is None:
            raise ApiError(
                status=404, title="Not found", detail=f"Table {table_name!r} not found."
            )

        col_rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """,
            table_name,
        )

        pk_rows = await conn.fetch(
            """
            SELECT a.attname AS column_name
            FROM   pg_index i
            JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE  i.indrelid = $1::regclass AND i.indisprimary
            """,
            f"public.{table_name}",
        )
        pks = {r["column_name"] for r in pk_rows}

        fk_rows = await conn.fetch(
            """
            SELECT kcu.column_name,
                   ccu.table_name AS foreign_table,
                   ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
               AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = $1
            """,
            table_name,
        )
        fks = {
            r["column_name"]: FkRef(table=r["foreign_table"], column=r["foreign_column"])
            for r in fk_rows
        }

        row_count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')

        columns = [
            ColumnOut(
                name=r["column_name"],
                type=r["data_type"],
                nullable=(r["is_nullable"] == "YES"),
                is_pk=r["column_name"] in pks,
                fk=fks.get(r["column_name"]),
            )
            for r in col_rows
        ]

    return TableDetail(
        name=table_name,
        columns=columns,
        row_count=int(row_count or 0),
        editable=False,
    )


def _encode_cursor(value: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps({"v": value}, default=str).encode()).decode()


def _decode_cursor(cursor: str) -> Any:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    return json.loads(raw)["v"]


@router.get("/tables/{table_name}/rows", response_model=RowsPage)
async def get_rows(
    project_id: str,
    table_name: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> RowsPage:
    detail = await get_table(project_id, table_name)
    pk_columns = [c.name for c in detail.columns if c.is_pk]

    db_name = await _resolve_project_db(project_id)
    pool = await get_pools().project(db_name)

    col_names = [c.name for c in detail.columns]
    select_cols = ", ".join(f'"{c}"' for c in col_names)

    async with pool.acquire() as conn:
        if pk_columns:
            pk = pk_columns[0]
            args: list[Any] = [limit]
            where = ""
            if cursor:
                cursor_val = _decode_cursor(cursor)
                args.append(cursor_val)
                where = f'WHERE "{pk}" > $2'
            sql = f'SELECT {select_cols} FROM "{table_name}" {where} ORDER BY "{pk}" ASC LIMIT $1'
            rows = await conn.fetch(sql, *args)
            next_cursor = None
            if len(rows) == limit:
                last = rows[-1][pk]
                next_cursor = _encode_cursor(last)
        else:
            # No PK: degrade to offset pagination.
            offset = int(cursor) if cursor and cursor.isdigit() else 0
            sql = f'SELECT {select_cols} FROM "{table_name}" LIMIT $1 OFFSET $2'
            rows = await conn.fetch(sql, limit, offset)
            next_cursor = str(offset + limit) if len(rows) == limit else None

    serialized = [[_jsonable(v) for v in row.values()] for row in rows]
    return RowsPage(columns=col_names, rows=serialized, next_cursor=next_cursor)


def _jsonable(v: Any) -> Any:
    """Convert types that aren't JSON-native (UUID, datetime, Decimal, ...) to strings."""

    if v is None or isinstance(v, str | int | float | bool):
        return v
    return str(v)
