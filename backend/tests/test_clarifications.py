from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from structai.db import clarifications_repo, runs_repo
from structai.db.ids import new_id

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _setup_run(client: AsyncClient) -> str:
    r = await client.post("/api/projects", json={"name": "Clar"})
    pid = r.json()["id"]
    up = await client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    did = up.json()["id"]
    run_id = new_id()
    await runs_repo.create_run(
        run_id=run_id, project_id=pid, document_id=did,
        title="x.csv", instructions=None, auto_mode=False,
    )
    await runs_repo.set_run_status(run_id=run_id, status="needs_clarification")
    return run_id


@pytest.mark.asyncio
async def test_list_and_answer(client: AsyncClient) -> None:
    run_id = await _setup_run(client)
    clar_id = new_id()
    await clarifications_repo.create_clarification(
        clar_id=clar_id,
        run_id=run_id,
        question="Which key is the PK?",
        context="Two integer columns are unique.",
        options=[
            {"id": "id", "label": "id", "description": "the first column"},
            {"id": "user_id", "label": "user_id"},
        ],
    )

    listing = await client.get(f"/api/runs/{run_id}/clarifications")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    # Verify clarifications also appear in the run response.
    snap = await client.get(f"/api/runs/{run_id}")
    assert len(snap.json()["clarifications"]) == 1

    # Answer it.
    ans = await client.post(
        f"/api/runs/{run_id}/clarifications/{clar_id}/answer",
        json={"choice_id": "id"},
    )
    assert ans.status_code == 200, ans.text
    body = ans.json()
    assert body["answer_choice_id"] == "id"
    assert body["answered_at"] is not None

    # Double-answer rejected.
    again = await client.post(
        f"/api/runs/{run_id}/clarifications/{clar_id}/answer",
        json={"choice_id": "user_id"},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_answer_unknown_clarification(client: AsyncClient) -> None:
    run_id = await _setup_run(client)
    r = await client.post(
        f"/api/runs/{run_id}/clarifications/missing/answer",
        json={"choice_id": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_answer_requires_choice_or_custom(client: AsyncClient) -> None:
    run_id = await _setup_run(client)
    clar_id = new_id()
    await clarifications_repo.create_clarification(
        clar_id=clar_id, run_id=run_id, question="?", context=None,
        options=[{"id": "a", "label": "A"}],
    )
    r = await client.post(
        f"/api/runs/{run_id}/clarifications/{clar_id}/answer",
        json={},
    )
    assert r.status_code == 400
