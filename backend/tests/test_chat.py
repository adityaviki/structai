from __future__ import annotations

from typing import TYPE_CHECKING, Any

import asyncpg
import pytest

from structai.agent import chat as chat_module
from structai.db.pool import with_database
from structai.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from httpx import AsyncClient


async def _setup_people(client: AsyncClient) -> tuple[str, str]:
    r = await client.post("/api/projects", json={"name": "Chat test"})
    pid = r.json()["id"]
    db_name = r.json()["db_name"]
    conn = await asyncpg.connect(with_database(get_settings().pg_url, db_name))
    try:
        await conn.execute(
            """
            CREATE TABLE people (
                id    integer PRIMARY KEY,
                name  text NOT NULL,
                email text
            );
            INSERT INTO people VALUES
                (1, 'Alice', 'Alice@X.com'),
                (2, 'Bob',   'BOB@x.com'),
                (3, 'Carol', 'carol@x.com');
            """
        )
    finally:
        await conn.close()
    return pid, db_name


async def _emails(db_name: str) -> list[str]:
    conn = await asyncpg.connect(with_database(get_settings().pg_url, db_name))
    try:
        rows = await conn.fetch("SELECT email FROM people ORDER BY id")
        return [r["email"] for r in rows]
    finally:
        await conn.close()


_LOWERCASE_CHANGE: dict[str, Any] = {
    "reply": "I'll lowercase the email addresses.",
    "change": {
        "target_table": "people",
        "summary": "Lowercase every email address.",
        "sql": "UPDATE people SET email = lower(email) WHERE email <> lower(email);",
        "preview": [{"column": "email", "before": "Alice@X.com", "after": "alice@x.com"}],
    },
}


def _stub_loop(
    result: dict[str, Any],
    *,
    call_tool: tuple[str, dict[str, Any]] | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Replace ``agentic_loop`` with a canned result.

    When ``call_tool`` is given, first invoke the real tool handler (to exercise
    read-only SQL execution) and return its text as the reply.
    """

    async def loop(**kwargs: Any) -> dict[str, Any]:
        if call_tool is not None:
            name, payload = call_tool
            tool_out = await kwargs["handle_tool_call"](name, payload)
            return {"reply": tool_out}
        return result

    return loop


@pytest.mark.asyncio
async def test_chat_question_no_change(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pid, _ = await _setup_people(client)
    monkeypatch.setattr(chat_module, "agentic_loop", _stub_loop({"reply": "There are 3 people."}))

    r = await client.post(f"/api/projects/{pid}/chat", json={"message": "how many people?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "agent"
    assert body["change"] is None
    assert "3" in body["content"]

    thread = (await client.get(f"/api/projects/{pid}/chat")).json()["messages"]
    assert [m["role"] for m in thread] == ["user", "agent"]
    assert thread[0]["content"] == "how many people?"


@pytest.mark.asyncio
async def test_chat_propose_apply_undo(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid, db_name = await _setup_people(client)
    monkeypatch.setattr(chat_module, "agentic_loop", _stub_loop(_LOWERCASE_CHANGE))

    r = await client.post(f"/api/projects/{pid}/chat", json={"message": "lowercase the emails"})
    assert r.status_code == 200, r.text
    change = r.json()["change"]
    assert change is not None
    assert change["status"] == "proposing"
    assert change["target_table"] == "people"
    # Dry-run computes the exact count: Alice@X.com and BOB@x.com change; carol stays.
    assert change["affected_rows"] == 2
    assert change["total_rows"] == 3
    change_id = change["id"]

    applied = await client.post(f"/api/projects/{pid}/changes/{change_id}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    assert applied.json()["snapshot_available"] is True
    assert await _emails(db_name) == ["alice@x.com", "bob@x.com", "carol@x.com"]

    undone = await client.post(f"/api/projects/{pid}/changes/{change_id}/undo")
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "reverted"
    assert undone.json()["snapshot_available"] is False
    assert await _emails(db_name) == ["Alice@X.com", "BOB@x.com", "carol@x.com"]


@pytest.mark.asyncio
async def test_chat_reject(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pid, db_name = await _setup_people(client)
    monkeypatch.setattr(chat_module, "agentic_loop", _stub_loop(_LOWERCASE_CHANGE))

    change = (
        await client.post(f"/api/projects/{pid}/chat", json={"message": "lowercase emails"})
    ).json()["change"]
    change_id = change["id"]

    rejected = await client.post(f"/api/projects/{pid}/changes/{change_id}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    # Nothing changed, and a rejected change can't be applied.
    assert await _emails(db_name) == ["Alice@X.com", "BOB@x.com", "carol@x.com"]
    retry = await client.post(f"/api/projects/{pid}/changes/{change_id}/apply")
    assert retry.status_code == 409


@pytest.mark.asyncio
async def test_read_only_tool_rejects_write(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid, db_name = await _setup_people(client)
    monkeypatch.setattr(
        chat_module,
        "agentic_loop",
        _stub_loop({}, call_tool=("run_read_sql", {"sql": "UPDATE people SET email = 'zzz'"})),
    )

    r = await client.post(f"/api/projects/{pid}/chat", json={"message": "wipe the emails"})
    assert r.status_code == 200, r.text
    assert "read-only" in r.json()["content"].lower()
    # The write must not have landed.
    assert await _emails(db_name) == ["Alice@X.com", "BOB@x.com", "carol@x.com"]
