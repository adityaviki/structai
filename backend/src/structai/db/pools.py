"""Async connection pool management.

Two flavors:

- A single shared pool to ``structai_meta`` for app metadata.
- A lazily-created pool per project database, cached in a dict and closable
  on shutdown.

We use asyncpg directly (no SQLAlchemy) for the low-level control we'll
need in Phase 2 (draining pools to run ``CREATE DATABASE ... TEMPLATE``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg

from .pool import with_database

if TYPE_CHECKING:
    from ..settings import Settings


class Pools:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._meta: asyncpg.Pool | None = None
        self._projects: dict[str, asyncpg.Pool] = {}

    async def meta(self) -> asyncpg.Pool:
        if self._meta is None:
            self._meta = await asyncpg.create_pool(
                with_database(self._settings.pg_url, self._settings.meta_db_name),
                min_size=1,
                max_size=10,
            )
        return self._meta

    async def project(self, db_name: str) -> asyncpg.Pool:
        pool = self._projects.get(db_name)
        if pool is None:
            pool = await asyncpg.create_pool(
                with_database(self._settings.pg_url, db_name),
                min_size=1,
                max_size=10,
            )
            self._projects[db_name] = pool
        return pool

    async def drop_project_pool(self, db_name: str) -> None:
        """Close and forget a per-project pool (used before DROP DATABASE)."""

        pool = self._projects.pop(db_name, None)
        if pool is not None:
            await pool.close()

    async def close(self) -> None:
        for pool in self._projects.values():
            await pool.close()
        self._projects.clear()
        if self._meta is not None:
            await self._meta.close()
            self._meta = None


_pools: Pools | None = None


def init_pools(settings: Settings) -> Pools:
    global _pools
    _pools = Pools(settings)
    return _pools


def get_pools() -> Pools:
    if _pools is None:
        raise RuntimeError("Pools not initialized; call init_pools() in lifespan first.")
    return _pools
