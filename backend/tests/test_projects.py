from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_project(client: AsyncClient) -> None:
    r = await client.post(
        "/api/projects",
        json={"name": "Sales 2024", "emoji": "📊"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Sales 2024"
    assert created["db_name"].startswith("structai_sales_2024_")

    r2 = await client.get("/api/projects")
    assert r2.status_code == 200
    projects = r2.json()
    assert len(projects) == 1
    assert projects[0]["id"] == created["id"]
    assert projects[0]["stats"] == {"tables": 0, "documents": 0, "imports_completed": 0}


@pytest.mark.asyncio
async def test_get_project_not_found(client: AsyncClient) -> None:
    r = await client.get("/api/projects/does_not_exist")
    assert r.status_code == 404
    body = r.json()
    assert body["title"] == "Not found"


@pytest.mark.asyncio
async def test_get_project_roundtrip(client: AsyncClient) -> None:
    r = await client.post("/api/projects", json={"name": "HR"})
    pid = r.json()["id"]
    r2 = await client.get(f"/api/projects/{pid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "HR"
