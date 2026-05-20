"""SQLAlchemy models for every table in plan §4.

State enums and load-mode strings are validated by CHECK constraints in the
migration. Invariants worth remembering (plan §4, §6.4, §8.4):

- `pipeline_revisions.ir_jsonb / ir_sha256 / parent_id / created_by` never
  change once written. User edits / agent re-emissions create a new row.
  Only `state` mutates in place.
- `jobs` always carries a lease; the worker heartbeats while running and
  the reaper recycles jobs whose `lease_expires_at` has passed.
- `event_log.id` is a monotonic bigserial per session so SSE clients can
  resume via `Last-Event-ID`.
- `import_runs.id` is allocated before any staging table; retry policy is
  keyed by `import_runs.status` (§8.4).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from structai_core.db.base import Base

# --- State / kind vocabularies (matched by CHECK constraints in the migration) ---

PIPELINE_REVISION_STATES = (
    "proposed_ir",
    "user_edited_ir",
    "validated_ir",
    "dry_run_passed",
    "approved_for_execution",
    "executed",
)
PIPELINE_REVISION_CREATED_BY = ("agent", "user_edit")
PIPELINE_ARTIFACT_KINDS = ("pipeline_py", "manifest_json", "dry_run_report")
JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")
JOB_ERROR_CLASSES = ("retryable", "terminal")
IMPORT_RUN_STATUSES = (
    "pending",
    "running",
    "committed",
    "failed_before_commit",
    "cancelled",
)
AGENT_SESSION_STATUSES = ("in_progress", "completed", "error")
LOAD_MODES = ("append", "replace", "upsert", "fail_if_duplicate", "merge", "version")


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    quarantine_path: Mapped[str | None] = mapped_column(Text)
    live_path: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retention_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cost_tokens_in: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)
    cost_tokens_out: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="in_progress", nullable=False)


class PipelineRevision(Base):
    __tablename__ = "pipeline_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("pipeline_revisions.id", ondelete="SET NULL"),
    )
    ir_version: Mapped[str] = mapped_column(Text, nullable=False)
    ir_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ir_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PipelineArtifact(Base):
    __tablename__ = "pipeline_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    revision_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pipeline_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="queued", nullable=False)
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3", nullable=False)
    error_class: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_jobs_kind_status", "kind", "status"),
    )


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_event_log_session_id_id", "session_id", "id"),)


class EventCursor(Base):
    __tablename__ = "event_cursors"

    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    client_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    revision_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pipeline_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    dry_run_only: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)


class ImportRunTable(Base):
    __tablename__ = "import_run_tables"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    load_mode: Mapped[str] = mapped_column(Text, nullable=False)
    rows_inserted: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)
    rows_updated: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)
    rows_rejected: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)


class RejectedRowArtifact(Base):
    __tablename__ = "rejected_row_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id_table_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_run_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PipelineRegistry(Base):
    """Fingerprint index for pipeline reuse (populated in v1.3, plan §9)."""

    __tablename__ = "pipeline_registry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    revision_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pipeline_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_seen_file_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("files.id", ondelete="SET NULL"),
    )
