from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import pytest

from structai.db.pool import with_database
from structai.settings import get_settings

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _setup_table(client: AsyncClient) -> str:
    r = await client.post("/api/projects", json={"name": "Filter test"})
    pid = r.json()["id"]
    db_name = r.json()["db_name"]
    s = get_settings()
    conn = await asyncpg.connect(with_database(s.pg_url, db_name))
    try:
        await conn.execute(
            """
            CREATE TABLE people (
                id integer PRIMARY KEY,
                name text NOT NULL,
                age integer
            );
            INSERT INTO people VALUES
                (1,'Alice',30),
                (2,'Bob',25),
                (3,'Carol',42),
                (4,'Daniel',18),
                (5,'Eve',NULL);
            """
        )
    finally:
        await conn.close()
    return pid


@pytest.mark.asyncio
async def test_filter_contains_and_sort(client: AsyncClient) -> None:
    pid = await _setup_table(client)
    r = await client.get(
        f"/api/projects/{pid}/tables/people/rows",
        params={"filter": "name:contains:a", "sort": "age", "dir": "desc"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    # 'a' should match Alice, Carol, Daniel (case-insensitive). Sorted by age desc:
    # Carol(42) > Alice(30) > Daniel(18).
    names = [row[1] for row in rows]
    assert names == ["Carol", "Alice", "Daniel"]


@pytest.mark.asyncio
async def test_filter_range(client: AsyncClient) -> None:
    pid = await _setup_table(client)
    r = await client.get(
        f"/api/projects/{pid}/tables/people/rows",
        params=[("filter", "age:gte:25"), ("filter", "age:lt:42")],
    )
    assert r.status_code == 200, r.text
    names = sorted(row[1] for row in r.json()["rows"])
    assert names == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_filter_unknown_column_400(client: AsyncClient) -> None:
    pid = await _setup_table(client)
    r = await client.get(
        f"/api/projects/{pid}/tables/people/rows",
        params={"filter": "ghost:eq:x"},
    )
    assert r.status_code == 400
