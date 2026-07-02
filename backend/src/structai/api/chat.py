"""Chat data-agent API: converse over a project's imported data and apply,
undo, or reject the changes the agent proposes.

Applied changes reuse the import-undo snapshot machinery (D15): each apply
clones the project DB first, and only the most-recently-applied change keeps
its snapshot, so it is one-click reversible.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from ..agent.chat import (
    change_record_to_out,
    message_record_to_out,
    parse_status_count,
    run_chat_turn,
)
from ..db import chat_repo
from ..db.pools import get_pools
from ..db.snapshots import (
    create_snapshot,
    drop_snapshot,
    restore_from_snapshot,
    snapshot_name,
)
from ..logging import log
from ..schemas.chat import ChatMessageOut, ChatThreadOut, ChatTurnIn, ProposedChangeOut
from ..settings import get_settings
from .errors import ApiError

router = APIRouter(prefix="/api/projects/{project_id}", tags=["chat"])

# Upper bound on how long an applied change may run before Postgres aborts it.
_APPLY_TIMEOUT = "60s"


async def _require_project_db(project_id: str) -> str:
    db_name = await chat_repo.get_project_db(project_id)
    if db_name is None:
        raise ApiError(status=404, title="Not found", detail=f"Project {project_id!r} not found.")
    assert isinstance(db_name, str)
    return db_name


@router.get("/chat", response_model=ChatThreadOut)
async def get_chat(project_id: str) -> ChatThreadOut:
    await _require_project_db(project_id)
    messages = await chat_repo.list_messages(project_id)
    change_ids = [m["change_id"] for m in messages if m["change_id"]]
    changes = {c["id"]: c for c in await chat_repo.get_changes(change_ids)}
    out: list[ChatMessageOut] = []
    for m in messages:
        cid = m["change_id"]
        change = change_record_to_out(changes[cid]) if cid and cid in changes else None
        out.append(message_record_to_out(m, change))
    return ChatThreadOut(messages=out)


@router.post("/chat", response_model=ChatMessageOut)
async def post_chat(project_id: str, body: ChatTurnIn) -> ChatMessageOut:
    db_name = await _require_project_db(project_id)
    message = body.message.strip()
    if not message:
        raise ApiError(status=400, title="Bad request", detail="Message is empty.")
    try:
        return await run_chat_turn(project_id=project_id, db_name=db_name, message=message)
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 -- turn into a readable problem response
        log.exception("chat.turn_failed", project_id=project_id)
        raise ApiError(
            status=502,
            title="Agent error",
            detail=f"The agent could not complete this turn: {exc}",
        ) from exc


async def _load_change(project_id: str, change_id: str) -> ProposedChangeOut:
    row = await chat_repo.get_change(change_id)
    if row is None or row["project_id"] != project_id:
        raise ApiError(
            status=404,
            title="Not found",
            detail=f"Change {change_id!r} not found in project {project_id!r}.",
        )
    return change_record_to_out(row)


@router.post("/changes/{change_id}/apply", response_model=ProposedChangeOut)
async def apply_change(project_id: str, change_id: str) -> ProposedChangeOut:
    db_name = await _require_project_db(project_id)
    row = await chat_repo.get_change(change_id)
    if row is None or row["project_id"] != project_id:
        raise ApiError(status=404, title="Not found", detail=f"Change {change_id!r} not found.")
    if row["status"] != "proposing":
        raise ApiError(
            status=409,
            title="Not applicable",
            detail=f"This change is already {row['status']}.",
        )

    settings = get_settings()

    # The change currently holding the project's undo snapshot — we'll retire it
    # once the new change lands (only the latest applied change stays undoable).
    prev = await chat_repo.change_holding_snapshot(project_id)

    snap_db = snapshot_name(db_name, change_id)
    await create_snapshot(settings=settings, project_db=db_name, snapshot_db=snap_db)

    pool = await get_pools().project(db_name)
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(f"SET LOCAL statement_timeout = '{_APPLY_TIMEOUT}'")
            status = await conn.execute(row["sql"])
    except Exception as exc:  # noqa: BLE001 -- report the failure, keep DB pristine
        await drop_snapshot(settings=settings, snapshot_db=snap_db)
        await chat_repo.set_change_status(change_id=change_id, status="failed")
        raise ApiError(status=400, title="Change failed", detail=str(exc)) from exc

    affected = parse_status_count(status)
    now = datetime.now(UTC)
    await chat_repo.set_change_status(
        change_id=change_id,
        status="applied",
        snapshot_db=snap_db,
        applied_at=now,
        affected_rows=affected if affected is not None else row["affected_rows"],
    )

    if prev is not None and prev["id"] != change_id and prev["snapshot_db"]:
        try:
            await drop_snapshot(settings=settings, snapshot_db=prev["snapshot_db"])
        except Exception:  # noqa: BLE001
            log.exception("chat.prev_snapshot_drop_failed", change_id=prev["id"])
        await chat_repo.set_change_status(change_id=prev["id"], clear_snapshot=True)

    log.info("chat.change_applied", project_id=project_id, change_id=change_id, affected=affected)
    return await _load_change(project_id, change_id)


@router.post("/changes/{change_id}/undo", response_model=ProposedChangeOut)
async def undo_change(project_id: str, change_id: str) -> ProposedChangeOut:
    db_name = await _require_project_db(project_id)
    row = await chat_repo.get_change(change_id)
    if row is None or row["project_id"] != project_id:
        raise ApiError(status=404, title="Not found", detail=f"Change {change_id!r} not found.")
    if row["status"] != "applied" or not row["snapshot_db"]:
        raise ApiError(
            status=409,
            title="Not undoable",
            detail="Only the most recently applied change can be undone (snapshot expired).",
        )

    settings = get_settings()
    await restore_from_snapshot(
        settings=settings, project_db=db_name, snapshot_db=row["snapshot_db"],
    )
    await chat_repo.set_change_status(
        change_id=change_id,
        status="reverted",
        reverted_at=datetime.now(UTC),
        clear_snapshot=True,
    )
    log.info("chat.change_reverted", project_id=project_id, change_id=change_id)
    return await _load_change(project_id, change_id)


@router.post("/changes/{change_id}/reject", response_model=ProposedChangeOut)
async def reject_change(project_id: str, change_id: str) -> ProposedChangeOut:
    await _require_project_db(project_id)
    row = await chat_repo.get_change(change_id)
    if row is None or row["project_id"] != project_id:
        raise ApiError(status=404, title="Not found", detail=f"Change {change_id!r} not found.")
    if row["status"] != "proposing":
        raise ApiError(
            status=409,
            title="Not rejectable",
            detail=f"This change is already {row['status']}.",
        )
    await chat_repo.set_change_status(change_id=change_id, status="rejected")
    return await _load_change(project_id, change_id)
