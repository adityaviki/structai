from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _create_project(client: AsyncClient, name: str = "Demo") -> str:
    r = await client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_upload_csv_and_list(client: AsyncClient) -> None:
    pid = await _create_project(client)
    csv = b"id,name\n1,Alice\n2,Bob\n"
    r = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("people.csv", io.BytesIO(csv), "text/csv")},
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["ext"] == "csv"
    assert doc["size_bytes"] == len(csv)
    assert doc["status"] == "uploaded"

    listing = await client.get(f"/api/projects/{pid}/documents")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


@pytest.mark.asyncio
async def test_upload_rejects_non_csv(client: AsyncClient) -> None:
    pid = await _create_project(client)
    r = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("data.xlsx", io.BytesIO(b"PK"), "application/octet-stream")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_upload_unknown_project(client: AsyncClient) -> None:
    r = await client.post(
        "/api/projects/missing/documents",
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert r.status_code == 404
