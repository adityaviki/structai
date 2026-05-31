"""Introspect a project's live Postgres schema and format it for the LLM.

Used both by the orchestrator (to feed `generate` / `fix` the existing
schema) and by the API's schema-diagram endpoint (deferred — see
``api/schema.py``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .pools import get_pools


@dataclass(slots=True)
class IntrospectedColumn:
    name: str
    type: str
    nullable: bool
    is_pk: bool
    fk_table: str | None
    fk_column: str | None


@dataclass(slots=True)
class IntrospectedTable:
    name: str
    columns: list[IntrospectedColumn]
    row_count: int


async def introspect_project(db_name: str) -> list[IntrospectedTable]:
    """Return every public table in the project DB with columns + PK + FKs."""

    pool = await get_pools().project(db_name)
    async with pool.acquire() as conn:
        table_rows = await conn.fetch(
            """
            SELECT c.relname AS name
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY c.relname
            """
        )
        col_rows = await conn.fetch(
            """
            SELECT table_name, column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
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

        row_counts: dict[str, int] = {}
        for tr in table_rows:
            n = await conn.fetchval(f'SELECT COUNT(*) FROM "{tr["name"]}"')
            row_counts[tr["name"]] = int(n or 0)

    pks: dict[str, set[str]] = {}
    for r in pk_rows:
        pks.setdefault(r["table_name"], set()).add(r["column_name"])

    fks: dict[tuple[str, str], tuple[str, str]] = {}
    for r in fk_rows:
        fks[(r["src_table"], r["src_column"])] = (r["dst_table"], r["dst_column"])

    by_table: dict[str, list[IntrospectedColumn]] = {}
    for cr in col_rows:
        fk = fks.get((cr["table_name"], cr["column_name"]))
        by_table.setdefault(cr["table_name"], []).append(
            IntrospectedColumn(
                name=cr["column_name"],
                type=cr["data_type"],
                nullable=(cr["is_nullable"] == "YES"),
                is_pk=cr["column_name"] in pks.get(cr["table_name"], set()),
                fk_table=fk[0] if fk else None,
                fk_column=fk[1] if fk else None,
            )
        )

    return [
        IntrospectedTable(
            name=tr["name"],
            columns=by_table.get(tr["name"], []),
            row_count=row_counts.get(tr["name"], 0),
        )
        for tr in table_rows
    ]


def format_for_llm(tables: list[IntrospectedTable]) -> str:
    """Compact text rendering of the schema for inclusion in a prompt."""

    if not tables:
        return ""

    out: list[str] = []
    for t in tables:
        out.append(f"{t.name} ({t.row_count} rows)")
        # Column type widths for readability.
        name_w = max((len(c.name) for c in t.columns), default=0)
        for c in t.columns:
            bits: list[str] = [c.type]
            if not c.nullable:
                bits.append("NOT NULL")
            if c.is_pk:
                bits.append("PRIMARY KEY")
            if c.fk_table:
                bits.append(f"REFERENCES {c.fk_table}({c.fk_column})")
            out.append(f"  {c.name.ljust(name_w)}  {' '.join(bits)}")
        out.append("")
    return "\n".join(out).rstrip()
