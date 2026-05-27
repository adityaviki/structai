from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import pytest

from structai.db.pool import with_database
from structai.settings import get_settings

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _setup_two_table_schema(client: AsyncClient) -> str:
    r = await client.post("/api/projects", json={"name": "Schema test"})
    pid = r.json()["id"]
    db_name = r.json()["db_name"]
    settings = get_settings()
    conn = await asyncpg.connect(with_database(settings.pg_url, db_name))
    try:
        await conn.execute(
            """
            CREATE TABLE customers (
                id      integer PRIMARY KEY,
                name    text    NOT NULL,
                email   text
            );
            CREATE TABLE orders (
                id           integer PRIMARY KEY,
                customer_id  integer REFERENCES customers(id),
                total        double precision
            );
            INSERT INTO customers (id, name, email) VALUES (1,'A','a@x'), (2,'B','b@x');
            INSERT INTO orders (id, customer_id, total) VALUES (10,1,9.99),(11,2,1.0);
            """
        )
    finally:
        await conn.close()
    return pid


@pytest.mark.asyncio
async def test_schema_endpoint(client: AsyncClient) -> None:
    pid = await _setup_two_table_schema(client)
    r = await client.get(f"/api/projects/{pid}/schema")
    assert r.status_code == 200, r.text
    body = r.json()
    by_name = {t["name"]: t for t in body["tables"]}
    assert set(by_name) == {"customers", "orders"}
    assert by_name["customers"]["row_count"] == 2
    assert by_name["orders"]["row_count"] == 2

    customer_pk = next(c for c in by_name["customers"]["columns"] if c["name"] == "id")
    assert customer_pk["is_pk"] is True

    fk_col = next(c for c in by_name["orders"]["columns"] if c["name"] == "customer_id")
    assert fk_col["fk"] == {"table": "customers", "column": "id"}


@pytest.mark.asyncio
async def test_layout_roundtrip(client: AsyncClient) -> None:
    pid = await _setup_two_table_schema(client)

    empty = await client.get(f"/api/projects/{pid}/schema/layout")
    assert empty.status_code == 200
    assert empty.json()["positions"] == []

    save = await client.post(
        f"/api/projects/{pid}/schema/layout",
        json={
            "positions": [
                {"table_name": "customers", "x": 0.0, "y": 100.0},
                {"table_name": "orders", "x": 400.0, "y": 100.0},
            ]
        },
    )
    assert save.status_code == 200, save.text
    saved = save.json()["positions"]
    by_table = {p["table_name"]: p for p in saved}
    assert by_table["customers"]["x"] == 0.0
    assert by_table["orders"]["x"] == 400.0

    # Idempotent upsert: re-saving updates rather than duplicates.
    save2 = await client.post(
        f"/api/projects/{pid}/schema/layout",
        json={"positions": [{"table_name": "customers", "x": 50.0, "y": 100.0}]},
    )
    again = {p["table_name"]: p for p in save2.json()["positions"]}
    assert again["customers"]["x"] == 50.0
    assert again["orders"]["x"] == 400.0  # untouched


@pytest.mark.asyncio
async def test_schema_unknown_project(client: AsyncClient) -> None:
    r = await client.get("/api/projects/nope/schema")
    assert r.status_code == 404
