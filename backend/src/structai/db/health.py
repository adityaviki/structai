from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import redis.asyncio as aioredis

from ..logging import log

if TYPE_CHECKING:
    from ..settings import Settings


class StartupCheckError(RuntimeError):
    """Raised when a required external service is unreachable on startup."""


async def check_postgres(settings: Settings) -> None:
    try:
        conn = await asyncpg.connect(settings.pg_url, timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        raise StartupCheckError(
            f"Cannot reach Postgres at {settings.pg_url!r}.\n"
            "  Hint: make sure Postgres is running and the role has CREATEDB.\n"
            "    pacman -S postgresql && systemctl --user start postgresql\n"
            "    createuser -s structai && createdb -O structai postgres\n"
            f"  Underlying error: {exc!s}"
        ) from exc
    try:
        # Confirm CREATEDB privilege so project creation works later.
        can_createdb = await conn.fetchval(
            "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"
        )
        if not can_createdb:
            raise StartupCheckError(
                f"Postgres role {await conn.fetchval('SELECT current_user')!r} "
                "lacks CREATEDB privilege. Grant with: ALTER ROLE <user> CREATEDB;"
            )
    finally:
        await conn.close()
    log.info("startup.postgres.ok", url=settings.pg_url)


async def check_redis(settings: Settings) -> None:
    client: aioredis.Redis = aioredis.from_url(settings.redis_url, socket_timeout=5)  # type: ignore[no-untyped-call]
    try:
        pong = await client.ping()
        if pong is not True:
            raise StartupCheckError(f"Redis at {settings.redis_url!r} did not PONG.")
    except (OSError, aioredis.RedisError) as exc:
        raise StartupCheckError(
            f"Cannot reach Redis at {settings.redis_url!r}.\n"
            "  Hint: install and start Redis.\n"
            "    pacman -S redis && systemctl --user start redis\n"
            f"  Underlying error: {exc!s}"
        ) from exc
    finally:
        await client.aclose()
    log.info("startup.redis.ok", url=settings.redis_url)


async def run_all(settings: Settings) -> None:
    await check_postgres(settings)
    await check_redis(settings)
