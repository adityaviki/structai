"""Request/response models for the chat data agent."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 -- pydantic needs it at runtime
from typing import Literal

from pydantic import BaseModel

ChatRole = Literal["user", "agent"]
DataChangeStatus = Literal["proposing", "applied", "rejected", "failed", "reverted"]


class ChangePreviewItem(BaseModel):
    column: str
    before: str
    after: str


class ProposedChangeOut(BaseModel):
    id: str
    target_table: str | None = None
    summary: str | None = None
    sql: str
    affected_rows: int | None = None
    total_rows: int | None = None
    preview: list[ChangePreviewItem] | None = None
    status: DataChangeStatus
    # True only while this change still owns a usable undo snapshot — i.e. it is
    # the most-recently-applied change. Drives the "Undo" affordance in the UI.
    snapshot_available: bool = False
    created_at: datetime
    applied_at: datetime | None = None
    reverted_at: datetime | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: ChatRole
    content: str
    change: ProposedChangeOut | None = None
    created_at: datetime


class ChatThreadOut(BaseModel):
    messages: list[ChatMessageOut]


class ChatTurnIn(BaseModel):
    message: str
