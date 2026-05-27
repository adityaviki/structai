"""Stage 4: lightweight validation of the imported tables.

Phase 1 checks:

- Each reported table exists in the project DB and has rows.
- The sum of row counts roughly matches what the script reported.
- Flag any column that's 100% NULL as a warning (not a failure).
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from ..db.pool import with_database
from ..settings import get_settings


@dataclass(slots=True)
class TableValidation:
    table: str
    row_count: int
    all_null_columns: list[str]


@dataclass(slots=True)
class ValidateResult:
    ok: bool
    tables: list[TableValidation]
    total_rows: int
    warnings: list[str]
    errors: list[str]


async def validate_project(
    *,
    db_name: str,
    reported_tables: list[str],
    reported_rows: int | None,
) -> ValidateResult:
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    warnings: list[str] = []
    errors: list[str] = []
    tables: list[TableValidation] = []
    total = 0

    try:
        for table in reported_tables:
            exists = await conn.fetchval(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table,
            )
            if exists is None:
                errors.append(f"Table {table!r} was reported but does not exist in the database.")
                continue

            row_count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
            assert isinstance(row_count, int)
            total += row_count

            col_rows = await conn.fetch(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table,
            )
            all_null: list[str] = []
            for cr in col_rows:
                col = cr["column_name"]
                non_null = await conn.fetchval(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 1'
                )
                if (non_null or 0) == 0 and row_count > 0:
                    all_null.append(col)

            if all_null:
                warnings.append(
                    f"Table {table!r} has columns that are 100% NULL: {', '.join(all_null)}"
                )
            tables.append(TableValidation(table=table, row_count=row_count, all_null_columns=all_null))
    finally:
        await conn.close()

    if reported_rows is not None and reported_rows != total:
        warnings.append(
            f"Script reported {reported_rows} rows imported but tables sum to {total}."
        )

    ok = not errors and total > 0
    if total == 0:
        errors.append("No rows were imported.")

    return ValidateResult(
        ok=ok,
        tables=tables,
        total_rows=total,
        warnings=warnings,
        errors=errors,
    )
