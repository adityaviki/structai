from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_settings_defaults(client: AsyncClient) -> None:
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    # `sk-test` is set in conftest env, so the key is present and source=env.
    assert body["anthropic_key_present"] is True
    assert body["anthropic_key_source"] == "env"
    assert body["default_model_source"] in {"env", "config", "default"}
    assert body["snapshot_keep_last_n"] >= 0


@pytest.mark.asyncio
async def test_patch_retention(client: AsyncClient) -> None:
    r = await client.patch(
        "/api/settings",
        json={"snapshot_keep_last_n": 5, "snapshot_max_age_days": 7},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot_keep_last_n"] == 5
    assert body["snapshot_max_age_days"] == 7


@pytest.mark.asyncio
async def test_project_model_override(client: AsyncClient) -> None:
    p = await client.post("/api/projects", json={"name": "ModelOverride"})
    pid = p.json()["id"]

    r = await client.put(
        f"/api/projects/{pid}/model",
        json={"model_override": "claude-opus-4-7"},
    )
    assert r.status_code == 200
    assert r.json()["model_override"] == "claude-opus-4-7"

    # Clearing.
    r2 = await client.put(
        f"/api/projects/{pid}/model",
        json={"model_override": None},
    )
    assert r2.status_code == 200
    assert r2.json()["model_override"] is None
