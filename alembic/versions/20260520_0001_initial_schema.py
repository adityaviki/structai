"""initial schema (plan §4)

Creates every table from plans/plan.md §4 plus the managed user schema
(default `structai_user`) where loaded tables will live (plan §8.2).
Vocabularies for state / kind columns are enforced by CHECK constraints
rather than Postgres ENUMs to keep evolution painless.

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20
"""

from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260520_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _check_in(col: str, values: Sequence[str], name: str) -> sa.CheckConstraint:
    values_sql = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{col} IN ({values_sql})", name=name)


def upgrade() -> None:
    # Managed schema where loaded tables go (plan §8.2). The name is configurable
    # via STRUCTAI_USER_SCHEMA; operators using a non-default name should ensure
    # the env var is set when running this migration.
    user_schema = os.environ.get("STRUCTAI_USER_SCHEMA", "structai_user")
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{user_schema}"')

    op.create_table(
        "files",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("original_name", sa.Text, nullable=False),
        sa.Column("bytes", sa.BigInteger, nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("quarantine_path", sa.Text),
        sa.Column("live_path", sa.Text),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "profiles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "file_id",
            sa.BigInteger,
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("profile_jsonb", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_profiles_file_id", "profiles", ["file_id"])

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "file_id",
            sa.BigInteger,
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("cost_tokens_in", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cost_tokens_out", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="in_progress"),
        _check_in("status", AGENT_SESSION_STATUSES, "ck_agent_sessions_status"),
    )
    op.create_index("ix_agent_sessions_file_id", "agent_sessions", ["file_id"])

    op.create_table(
        "pipeline_revisions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.BigInteger,
            sa.ForeignKey("pipeline_revisions.id", ondelete="SET NULL"),
        ),
        sa.Column("ir_version", sa.Text, nullable=False),
        sa.Column("ir_jsonb", postgresql.JSONB, nullable=False),
        sa.Column("ir_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("created_by", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        _check_in("state", PIPELINE_REVISION_STATES, "ck_pipeline_revisions_state"),
        _check_in("created_by", PIPELINE_REVISION_CREATED_BY, "ck_pipeline_revisions_created_by"),
    )
    op.create_index("ix_pipeline_revisions_session_id", "pipeline_revisions", ["session_id"])

    op.create_table(
        "pipeline_artifacts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "revision_id",
            sa.BigInteger,
            sa.ForeignKey("pipeline_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _check_in("kind", PIPELINE_ARTIFACT_KINDS, "ck_pipeline_artifacts_kind"),
    )
    op.create_index("ix_pipeline_artifacts_revision_id", "pipeline_artifacts", ["revision_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "payload_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("idempotency_key", sa.Text, unique=True),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.Text),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("error_class", sa.Text),
        sa.Column("last_error", sa.Text),
        sa.Column(
            "cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        _check_in("status", JOB_STATUSES, "ck_jobs_status"),
        sa.CheckConstraint(
            "error_class IS NULL OR error_class IN ("
            + ", ".join(f"'{v}'" for v in JOB_ERROR_CLASSES)
            + ")",
            name="ck_jobs_error_class",
        ),
    )
    op.create_index("ix_jobs_status_lease", "jobs", ["status", "lease_expires_at"])
    op.create_index("ix_jobs_kind_status", "jobs", ["kind", "status"])

    op.create_table(
        "event_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "payload_jsonb",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_event_log_session_id_id", "event_log", ["session_id", "id"])

    op.create_table(
        "event_cursors",
        sa.Column(
            "session_id",
            sa.BigInteger,
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("client_id", sa.Text, primary_key=True),
        sa.Column("last_event_id", sa.BigInteger, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "import_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "revision_id",
            sa.BigInteger,
            sa.ForeignKey("pipeline_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("dry_run_only", sa.Boolean, nullable=False, server_default=sa.false()),
        _check_in("status", IMPORT_RUN_STATUSES, "ck_import_runs_status"),
    )
    op.create_index("ix_import_runs_revision_id", "import_runs", ["revision_id"])

    op.create_table(
        "import_run_tables",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("import_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.Text, nullable=False),
        sa.Column("load_mode", sa.Text, nullable=False),
        sa.Column("rows_inserted", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("rows_rejected", sa.BigInteger, nullable=False, server_default="0"),
        _check_in("load_mode", LOAD_MODES, "ck_import_run_tables_load_mode"),
    )
    op.create_index("ix_import_run_tables_run_id", "import_run_tables", ["run_id"])

    op.create_table(
        "rejected_row_artifacts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id_table_id",
            sa.BigInteger,
            sa.ForeignKey("import_run_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("count", sa.BigInteger, nullable=False),
    )
    op.create_index(
        "ix_rejected_row_artifacts_run_id_table_id",
        "rejected_row_artifacts",
        ["run_id_table_id"],
    )

    op.create_table(
        "pipeline_registry",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "revision_id",
            sa.BigInteger,
            sa.ForeignKey("pipeline_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_file_id",
            sa.BigInteger,
            sa.ForeignKey("files.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    # Intentionally does NOT drop the managed user schema — it may hold loaded
    # tables the operator wants to keep. Drop it manually if truly desired.
    op.drop_table("pipeline_registry")
    op.drop_table("rejected_row_artifacts")
    op.drop_table("import_run_tables")
    op.drop_table("import_runs")
    op.drop_table("event_cursors")
    op.drop_table("event_log")
    op.drop_table("jobs")
    op.drop_table("pipeline_artifacts")
    op.drop_table("pipeline_revisions")
    op.drop_table("agent_sessions")
    op.drop_table("profiles")
    op.drop_table("files")
