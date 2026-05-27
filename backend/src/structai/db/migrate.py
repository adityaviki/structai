from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging import log
from ..settings import Settings, get_settings
from .pool import connect_meta, ensure_meta_db

if TYPE_CHECKING:
    import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
"""Resolves to backend/migrations regardless of where the package is installed."""

_FILENAME_RE = re.compile(r"^(\d{3,})_[a-z0-9_]+\.sql$")


def _list_migrations() -> list[tuple[int, Path]]:
    if not MIGRATIONS_DIR.exists():
        return []
    out: list[tuple[int, Path]] = []
    for entry in sorted(MIGRATIONS_DIR.iterdir()):
        m = _FILENAME_RE.match(entry.name)
        if not m:
            continue
        out.append((int(m.group(1)), entry))
    return out


async def _applied_versions(conn: asyncpg.Connection) -> set[int]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     integer PRIMARY KEY,
            filename    text    NOT NULL,
            applied_at  timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def migrate(settings: Settings | None = None) -> int:
    """Apply all pending migrations. Returns the count applied."""

    settings = settings or get_settings()
    await ensure_meta_db(settings)

    conn = await connect_meta(settings)
    applied = 0
    try:
        seen = await _applied_versions(conn)
        for version, path in _list_migrations():
            if version in seen:
                continue
            sql = path.read_text()
            log.info("migration.apply", version=version, filename=path.name)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
                    version,
                    path.name,
                )
            applied += 1
    finally:
        await conn.close()

    log.info("migration.done", applied=applied)
    return applied


def main() -> None:
    asyncio.run(migrate())


if __name__ == "__main__":
    main()
