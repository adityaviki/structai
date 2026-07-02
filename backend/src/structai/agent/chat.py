"""Chat data agent: run a conversational turn over a project's imported data.

The agent can inspect the data with a read-only SQL tool and, when the user
asks for a modification, propose a single reviewable change (persisted as a
``data_changes`` row in status ``proposing``). Applying / undoing the change is
handled by the API layer (``api/chat.py``), which reuses the snapshot machinery.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..db import chat_repo
from ..db.ids import new_id
from ..db.pools import get_pools
from ..db.schema_intro import format_for_llm, introspect_project
from ..schemas.chat import ChangePreviewItem, ChatMessageOut, ProposedChangeOut
from .client import agentic_loop
from .prompts import (
    CHAT_REPLY_TOOL,
    RUN_READ_SQL_TOOL,
    SYSTEM_CHAT,
    render_chat_user_message,
)

if TYPE_CHECKING:
    import asyncpg

# How many prior turns to feed back as context, and how many read-sql result
# rows to surface to the model. Bounded to keep token cost predictable.
_HISTORY_TURNS = 20
_MAX_READ_ROWS = 50


# ---------------------------------------------------------------------------
# Record -> Pydantic serialization (shared with api/chat.py)
# ---------------------------------------------------------------------------


def change_record_to_out(row: asyncpg.Record) -> ProposedChangeOut:
    raw_preview = row["preview"]
    if isinstance(raw_preview, str):
        raw_preview = json.loads(raw_preview)
    preview = (
        [
            ChangePreviewItem(
                column=str(p.get("column", "")),
                before=str(p.get("before", "")),
                after=str(p.get("after", "")),
            )
            for p in raw_preview
        ]
        if raw_preview
        else None
    )
    return ProposedChangeOut(
        id=row["id"],
        target_table=row["target_table"],
        summary=row["summary"],
        sql=row["sql"],
        affected_rows=row["affected_rows"],
        total_rows=row["total_rows"],
        preview=preview,
        status=row["status"],
        snapshot_available=(row["status"] == "applied" and row["snapshot_db"] is not None),
        created_at=row["created_at"],
        applied_at=row["applied_at"],
        reverted_at=row["reverted_at"],
    )


def message_record_to_out(
    row: asyncpg.Record,
    change: ProposedChangeOut | None,
) -> ChatMessageOut:
    return ChatMessageOut(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        change=change,
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def _format_rows(rows: list[asyncpg.Record], cap: int) -> str:
    if not rows:
        return "(0 rows)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows[:cap]:
        lines.append(" | ".join("NULL" if v is None else str(v) for v in r.values()))
    if len(rows) > cap:
        lines.append(f"... ({len(rows) - cap} more rows)")
    return "\n".join(lines)


async def _run_read_sql(pool: asyncpg.Pool, sql: str) -> str:
    """Execute one read-only query and render the rows as text for the model."""

    sql = (sql or "").strip()
    if not sql:
        return "Error: empty query."
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("SET LOCAL transaction_read_only = on")
            await conn.execute("SET LOCAL statement_timeout = '5s'")
            rows = await conn.fetch(sql)
    except Exception as exc:  # noqa: BLE001 -- surfaced back to the model as text
        return f"Query error: {exc}"
    return _format_rows(rows, _MAX_READ_ROWS)


def parse_status_count(status: str) -> int | None:
    """Pull the affected-row count out of an asyncpg command tag.

    e.g. "UPDATE 312" -> 312, "DELETE 5" -> 5, "INSERT 0 7" -> 7. DDL tags
    ("ALTER TABLE", "CREATE TABLE") carry no count -> None.
    """

    parts = status.split()
    if len(parts) >= 2 and parts[-1].isdigit() and parts[0] in {"UPDATE", "DELETE", "INSERT", "SELECT", "MERGE"}:
        return int(parts[-1])
    return None


async def _dry_run_counts(
    pool: asyncpg.Pool,
    target_table: str | None,
    sql: str,
    fallback: int | None,
) -> tuple[int | None, int | None]:
    """Run the proposed change inside a rolled-back transaction to learn the
    exact affected-row count, and count the target table. Best-effort: any
    failure leaves the model's estimate in place (apply will surface real errors).
    """

    affected = fallback
    total: int | None = None
    try:
        async with pool.acquire() as conn:
            if target_table:
                try:
                    n = await conn.fetchval(f'SELECT COUNT(*) FROM "{target_table}"')
                    total = int(n) if n is not None else None
                except Exception:  # noqa: BLE001
                    total = None
            tr = conn.transaction()
            await tr.start()
            try:
                await conn.execute("SET LOCAL statement_timeout = '15s'")
                status = await conn.execute(sql)
                parsed = parse_status_count(status)
                if parsed is not None:
                    affected = parsed
            finally:
                await tr.rollback()
    except Exception:  # noqa: BLE001
        pass
    return affected, total


# ---------------------------------------------------------------------------
# Turn driver
# ---------------------------------------------------------------------------


def _history_for_prompt(rows: list[asyncpg.Record]) -> list[dict[str, str]]:
    recent = rows[-_HISTORY_TURNS:]
    return [{"role": r["role"], "content": r["content"]} for r in recent if r["content"]]


async def _persist_change(
    *,
    project_id: str,
    pool: asyncpg.Pool,
    change: dict[str, Any],
) -> tuple[str, ProposedChangeOut]:
    target_table = change.get("target_table")
    sql = str(change["sql"])
    summary = change.get("summary")
    raw_preview = change.get("preview")
    preview: list[dict[str, str]] | None = None
    if isinstance(raw_preview, list):
        preview = [
            {
                "column": str(p.get("column", "")),
                "before": str(p.get("before", "")),
                "after": str(p.get("after", "")),
            }
            for p in raw_preview
            if isinstance(p, dict)
        ] or None

    estimate = change.get("affected_estimate")
    estimate = int(estimate) if isinstance(estimate, int) else None
    affected, total = await _dry_run_counts(pool, target_table, sql, estimate)

    change_id = new_id()
    await chat_repo.insert_change(
        change_id=change_id,
        project_id=project_id,
        target_table=target_table,
        summary=summary,
        sql=sql,
        affected_rows=affected,
        total_rows=total,
        preview=preview,
    )
    row = await chat_repo.get_change(change_id)
    assert row is not None
    return change_id, change_record_to_out(row)


async def run_chat_turn(*, project_id: str, db_name: str, message: str) -> ChatMessageOut:
    """Run one user turn: persist it, drive the agent, persist + return the reply."""

    tables = await introspect_project(db_name)
    schema_text = format_for_llm(tables)
    history = _history_for_prompt(await chat_repo.list_messages(project_id))

    await chat_repo.insert_message(
        message_id=new_id(), project_id=project_id, role="user", content=message,
    )

    pool = await get_pools().project(db_name)

    async def handle_tool_call(name: str, payload: dict[str, Any]) -> str:
        if name == "run_read_sql":
            return await _run_read_sql(pool, str(payload.get("sql", "")))
        return f"Unknown tool {name!r}."

    initial = render_chat_user_message(schema_text=schema_text, history=history, message=message)
    result = await agentic_loop(
        system=SYSTEM_CHAT,
        initial_user_blocks=[{"type": "text", "text": initial}],
        tools=[RUN_READ_SQL_TOOL, CHAT_REPLY_TOOL],
        terminal_tool_name="chat_reply",
        handle_tool_call=handle_tool_call,
    )

    reply_text = str(result.get("reply", "")).strip()
    change_payload = result.get("change")
    change_id: str | None = None
    change_out: ProposedChangeOut | None = None
    if isinstance(change_payload, dict) and change_payload.get("sql"):
        change_id, change_out = await _persist_change(
            project_id=project_id, pool=pool, change=change_payload,
        )

    agent_msg_id = new_id()
    await chat_repo.insert_message(
        message_id=agent_msg_id,
        project_id=project_id,
        role="agent",
        content=reply_text,
        change_id=change_id,
    )
    row = await chat_repo.get_message(agent_msg_id)
    assert row is not None
    return message_record_to_out(row, change_out)
