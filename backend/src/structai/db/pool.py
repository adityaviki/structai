from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import asyncpg

if TYPE_CHECKING:
    from ..settings import Settings


def with_database(pg_url: str, dbname: str) -> str:
    """Return the PG URL with its database path replaced by `dbname`."""

    parsed = urlparse(pg_url)
    # urlparse paths are like "/postgres"; ensure single leading slash.
    return urlunparse(parsed._replace(path=f"/{dbname}"))


async def connect_admin(settings: Settings) -> asyncpg.Connection:
    """Connect to the cluster's default database (for CREATE DATABASE etc.)."""

    return await asyncpg.connect(settings.pg_url)


async def connect_meta(settings: Settings) -> asyncpg.Connection:
    """Connect to the metadata database."""

    return await asyncpg.connect(with_database(settings.pg_url, settings.meta_db_name))


async def ensure_meta_db(settings: Settings) -> None:
    """Create the metadata database if it doesn't exist."""

    admin = await connect_admin(settings)
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings.meta_db_name,
        )
        if exists is None:
            # asyncpg requires literal DB names in CREATE DATABASE; quote safely.
            await admin.execute(f'CREATE DATABASE "{settings.meta_db_name}"')
    finally:
        await admin.close()
