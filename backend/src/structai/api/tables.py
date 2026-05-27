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


_FILTER_OPS = {
    "eq": "=",
    "neq": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "contains": "ILIKE",
}


_INT_TYPES = {"integer", "bigint", "smallint"}
_FLOAT_TYPES = {"double precision", "real", "numeric"}


def _coerce_value(raw_value: str, col_type: str) -> Any:
    t = col_type.lower()
    if t in _INT_TYPES:
        try:
            return int(raw_value)
        except ValueError as exc:
            raise ApiError(
                status=400, title="Bad filter", detail=f"Expected integer, got {raw_value!r}."
            ) from exc
    if t in _FLOAT_TYPES:
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ApiError(
                status=400, title="Bad filter", detail=f"Expected number, got {raw_value!r}."
            ) from exc
    if t == "boolean":
        if raw_value.lower() in {"true", "t", "1"}:
            return True
        if raw_value.lower() in {"false", "f", "0"}:
            return False
        raise ApiError(
            status=400, title="Bad filter", detail=f"Expected boolean, got {raw_value!r}."
        )
    # date / timestamp / timestamptz / text / uuid: pass through as string;
    # Postgres will parse ISO-8601 timestamps natively when bound to those
    # column types.
    return raw_value


def _parse_filters(
    raw: list[str],
    columns_by_name: dict[str, ColumnOut],
) -> list[tuple[str, str, Any]]:
    """Each `filter` query value is `col:op:value`. Coerces the value to the
    column's type so asyncpg can bind it directly.
    """

    out: list[tuple[str, str, Any]] = []
    for s in raw:
        parts = s.split(":", 2)
        if len(parts) != 3:
            raise ApiError(
                status=400, title="Bad filter", detail=f"Expected `col:op:value`, got {s!r}."
            )
        col, op, raw_value = parts
        if col not in columns_by_name:
            raise ApiError(status=400, title="Bad filter", detail=f"Unknown column {col!r}.")
        if op not in _FILTER_OPS:
            raise ApiError(
                status=400,
                title="Bad filter",
                detail=f"Unknown op {op!r}. Allowed: {', '.join(sorted(_FILTER_OPS))}.",
            )
        if op == "contains":
            out.append((col, op, raw_value))
        else:
            out.append((col, op, _coerce_value(raw_value, columns_by_name[col].type)))
    return out


@router.get("/tables/{table_name}/rows", response_model=RowsPage)
async def get_rows(
    project_id: str,
    table_name: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    sort: str | None = Query(default=None),
    dir: str = Query(default="asc"),
    filter: list[str] = Query(default=[]),  # noqa: A002, B008 -- FastAPI query arg
) -> RowsPage:
    detail = await get_table(project_id, table_name)
    pk_columns = [c.name for c in detail.columns if c.is_pk]
    col_names = [c.name for c in detail.columns]
    known = set(col_names)

    if sort is not None and sort not in known:
        raise ApiError(status=400, title="Bad sort", detail=f"Unknown column {sort!r}.")
    direction = dir.lower()
    if direction not in {"asc", "desc"}:
        raise ApiError(status=400, title="Bad sort", detail="`dir` must be asc or desc.")

    cols_by_name = {c.name: c for c in detail.columns}
    filters = _parse_filters(filter, cols_by_name)

    db_name = await _resolve_project_db(project_id)
    pool = await get_pools().project(db_name)
    select_cols = ", ".join(f'"{c}"' for c in col_names)

    # Build WHERE clause from filters.
    args: list[Any] = []
    where_parts: list[str] = []
    for col, op, raw_value in filters:
        sql_op = _FILTER_OPS[op]
        if op == "contains":
            args.append(f"%{raw_value}%")
            where_parts.append(f'"{col}"::text ILIKE ${len(args)}')
        else:
            args.append(raw_value)
            # Cast both sides to text for the typeless filter pipe; numeric/date
            # comparisons still work because Postgres reverses the cast.
            where_parts.append(f'"{col}" {sql_op} ${len(args)}')

    use_keyset = sort is None and not filters and bool(pk_columns)

    async with pool.acquire() as conn:
        if use_keyset:
            assert pk_columns
            pk = pk_columns[0]
            keyset_args: list[Any] = [limit]
            keyset_where = ""
            if cursor:
                cursor_val = _decode_cursor(cursor)
                keyset_args.append(cursor_val)
                keyset_where = f'WHERE "{pk}" > $2'
            sql = (
                f'SELECT {select_cols} FROM "{table_name}" {keyset_where} '
                f'ORDER BY "{pk}" ASC LIMIT $1'
            )
            rows = await conn.fetch(sql, *keyset_args)
            next_cursor = None
            if len(rows) == limit:
                next_cursor = _encode_cursor(rows[-1][pk])
        else:
            # Offset pagination for sort/filter cases (and PK-less tables).
            offset = int(cursor) if cursor and cursor.isdigit() else 0
            where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            order_col = sort if sort is not None else (pk_columns[0] if pk_columns else None)
            order_sql = (
                f'ORDER BY "{order_col}" {direction.upper()}'
                if order_col is not None
                else ""
            )
            limit_placeholder = f"${len(args) + 1}"
            offset_placeholder = f"${len(args) + 2}"
            sql = (
                f'SELECT {select_cols} FROM "{table_name}" {where_sql} {order_sql} '
                f'LIMIT {limit_placeholder} OFFSET {offset_placeholder}'
            )
            rows = await conn.fetch(sql, *args, limit, offset)
            next_cursor = str(offset + limit) if len(rows) == limit else None

    serialized = [[_jsonable(v) for v in row.values()] for row in rows]
    return RowsPage(columns=col_names, rows=serialized, next_cursor=next_cursor)


def _jsonable(v: Any) -> Any:
    """Convert types that aren't JSON-native (UUID, datetime, Decimal, ...) to strings."""

    if v is None or isinstance(v, str | int | float | bool):
        return v
    return str(v)
