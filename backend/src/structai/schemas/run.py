from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ImportStatus = Literal[
    "queued",
    "profiling",
    "generating",
    "executing",
    "fixing",
    "validating",
    "needs_clarification",
    "completed",
    "failed",
    "cancelling",
    "cancelled",
    "reverted",
]

PipelineStepKey = Literal["profile", "generate", "execute", "fix", "validate"]
PipelineStepStatus = Literal["pending", "running", "success", "error", "warning"]


class ImportRunIn(BaseModel):
    document_id: str
    instructions: str | None = None
    auto_mode: bool = False


class PipelineStepOut(BaseModel):
    key: PipelineStepKey
    title: str
    status: PipelineStepStatus
    summary: str | None = None
    code: str | None = None
    language: str | None = None
    attempts: int
    errors: list[str] | None = None
    started_at: datetime | None = None
    duration_ms: int | None = None


class ImportRunOut(BaseModel):
    id: str
    project_id: str
    document_id: str
    title: str
    status: ImportStatus
    progress: int
    started_at: datetime
    finished_at: datetime | None = None
    rows_imported: int | None = None
    total_rows: int | None = None
    created_tables: list[str] | None = None
    instructions: str | None = None
    auto_mode: bool
    error_message: str | None = None
    undo_available: bool = False
    reverted_at: datetime | None = None
    reverted_by_run_id: str | None = None
    steps: list[PipelineStepOut] = []
