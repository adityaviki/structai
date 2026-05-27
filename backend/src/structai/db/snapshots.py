"""Per-run snapshot helpers (D15).

Snapshots are full database clones created with ``CREATE DATABASE ...
TEMPLATE``. The PG file copy is fast but requires zero connections on the
template database, which is why we drain pools before each operation.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..logging import log
from .pool import connect_admin
from .pools import get_pools

if TYPE_CHECKING:
    import asyncpg

    from ..settings import Settings


async def _terminate_connections(admin: asyncpg.Connection, db_name: str) -> None:
    """Force-kill any backend connections to db_name.

    Defensive: pools should already be drained by the caller, but stray
    connections (e.g. psql sessions) can otherwise block CREATE/RENAME/DROP.
    """

    await admin.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = $1 AND pid <> pg_backend_pid()",
        db_name,
    )


async def create_snapshot(*, settings: Settings, project_db: str, snapshot_db: str) -> None:
    """Clone ``project_db`` into ``snapshot_db``. Pool is closed + reopened."""

    pools = get_pools()
    await pools.drop_project_pool(project_db)

    admin = await connect_admin(settings)
    try:
        await _terminate_connections(admin, project_db)
        await admin.execute(f'CREATE DATABASE "{snapshot_db}" TEMPLATE "{project_db}"')
    finally:
        await admin.close()

    # Re-prime the pool so subsequent steps don't pay a connection cold-start.
    await pools.project(project_db)
    log.info("snapshot.created", project_db=project_db, snapshot_db=snapshot_db)


async def drop_snapshot(*, settings: Settings, snapshot_db: str) -> None:
    """Drop a snapshot DB. Idempotent; safe to call on a missing DB."""

    admin = await connect_admin(settings)
    try:
        await _terminate_connections(admin, snapshot_db)
        await admin.execute(f'DROP DATABASE IF EXISTS "{snapshot_db}"')
    finally:
        await admin.close()
    log.info("snapshot.dropped", snapshot_db=snapshot_db)


async def restore_from_snapshot(
    *,
    settings: Settings,
    project_db: str,
    snapshot_db: str,
) -> None:
    """Atomic rename swap to restore the project DB from its snapshot.

    Steps (all pools must be closed first):

      1. Rename ``project_db`` to ``<project_db>_discard_<ts>``.
      2. Rename ``snapshot_db`` to ``project_db``.
      3. DROP the discarded DB.

    The window between steps 1 and 2 is the only moment the live DB name
    doesn't resolve. We make it as short as possible — two metadata-only
    ALTER DATABASE calls back-to-back.
    """

    pools = get_pools()
    await pools.drop_project_pool(project_db)
    await pools.drop_project_pool(snapshot_db)

    discard = f"{project_db}_discard_{int(time.time())}"
    admin = await connect_admin(settings)
    try:
        await _terminate_connections(admin, project_db)
        await _terminate_connections(admin, snapshot_db)
        await admin.execute(f'ALTER DATABASE "{project_db}" RENAME TO "{discard}"')
        await admin.execute(f'ALTER DATABASE "{snapshot_db}" RENAME TO "{project_db}"')
        await admin.execute(f'DROP DATABASE "{discard}"')
    finally:
        await admin.close()

    await pools.project(project_db)
    log.info("snapshot.restored", project_db=project_db, snapshot_db=snapshot_db)
