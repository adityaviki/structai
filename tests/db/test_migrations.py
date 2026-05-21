"""Migration verification.

The conftest's session-scoped fixture already ran `alembic upgrade head`
against `structai_test`, so most of these tests assert the post-upgrade
state directly. The downgrade round-trip uses a one-off DB to avoid
clobbering the shared test database.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from conftest import ADMIN_DSN, PG_HOST, PG_PASS, PG_PORT, PG_USER

EXPECTED_TABLES = {
    "files",
    "profiles",
    "agent_sessions",
    "pipeline_revisions",
    "pipeline_artifacts",
    "jobs",
    "event_log",
    "event_cursors",
    "import_runs",
    "import_run_tables",
    "rejected_row_artifacts",
    "pipeline_registry",
}

INITIAL_REVISION = "20260520_0001"


async def test_all_section4_tables_exist(db_session) -> None:
    res = await db_session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    )
    tables = {row[0] for row in res.all()}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


async def test_managed_user_schema_exists(db_session) -> None:
    res = await db_session.execute(
        text("SELECT nspname FROM pg_namespace WHERE nspname = 'structai_user'")
    )
    assert res.first() is not None


async def test_alembic_version_table_recorded(db_session) -> None:
    res = await db_session.execute(text("SELECT version_num FROM alembic_version"))
    assert res.scalar() == INITIAL_REVISION


async def test_jobs_status_indexes_exist(db_session) -> None:
    res = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'jobs'")
    )
    names = {row[0] for row in res.all()}
    assert "ix_jobs_status_lease" in names
    assert "ix_jobs_kind_status" in names


async def test_event_log_session_index_exists(db_session) -> None:
    res = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'event_log'")
    )
    assert "ix_event_log_session_id_id" in {row[0] for row in res.all()}


# --- CHECK constraints reject out-of-vocab values -------------------------------


async def test_jobs_status_check_rejects_invalid(db_session) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO jobs (kind, status, attempts, max_attempts) "
                "VALUES ('t', 'bogus', 0, 3)"
            )
        )
        await db_session.flush()


async def test_jobs_error_class_check_rejects_invalid(db_session) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO jobs (kind, error_class) VALUES ('t', 'maybe')")
        )
        await db_session.flush()


async def _seed_session(db_session) -> tuple[int, int]:
    """Insert a `files` + `agent_sessions` row; return both ids."""
    res = await db_session.execute(
        text(
            "INSERT INTO files (original_name, bytes, source_sha256) "
            "VALUES ('x.csv', 1, 'a') RETURNING id"
        )
    )
    file_id = res.scalar_one()
    res = await db_session.execute(
        text("INSERT INTO agent_sessions (file_id) VALUES (:f) RETURNING id"),
        {"f": file_id},
    )
    return file_id, res.scalar_one()


async def test_agent_sessions_status_check_rejects_invalid(db_session) -> None:
    res = await db_session.execute(
        text(
            "INSERT INTO files (original_name, bytes, source_sha256) "
            "VALUES ('x.csv', 1, 'a') RETURNING id"
        )
    )
    file_id = res.scalar_one()
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO agent_sessions (file_id, status) "
                "VALUES (:f, 'pondering')"
            ),
            {"f": file_id},
        )
        await db_session.flush()


async def test_pipeline_revisions_state_check_rejects_invalid(db_session) -> None:
    _, sess_id = await _seed_session(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO pipeline_revisions "
                "(session_id, ir_version, ir_jsonb, ir_sha256, state, created_by) "
                "VALUES (:s, 'v1', '{}'::jsonb, 'a', 'mystery_state', 'agent')"
            ),
            {"s": sess_id},
        )
        await db_session.flush()


async def test_pipeline_revisions_created_by_check_rejects_invalid(db_session) -> None:
    _, sess_id = await _seed_session(db_session)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO pipeline_revisions "
                "(session_id, ir_version, ir_jsonb, ir_sha256, state, created_by) "
                "VALUES (:s, 'v1', '{}'::jsonb, 'a', 'proposed_ir', 'ghost')"
            ),
            {"s": sess_id},
        )
        await db_session.flush()


async def test_pipeline_artifacts_kind_check_rejects_invalid(db_session) -> None:
    _, sess_id = await _seed_session(db_session)
    res = await db_session.execute(
        text(
            "INSERT INTO pipeline_revisions "
            "(session_id, ir_version, ir_jsonb, ir_sha256, state, created_by) "
            "VALUES (:s, 'v1', '{}'::jsonb, 'a', 'proposed_ir', 'agent') RETURNING id"
        ),
        {"s": sess_id},
    )
    rev_id = res.scalar_one()
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO pipeline_artifacts (revision_id, kind, path, sha256) "
                "VALUES (:r, 'magic_kind', '/p', 'h')"
            ),
            {"r": rev_id},
        )
        await db_session.flush()


async def test_import_runs_status_check_rejects_invalid(db_session) -> None:
    _, sess_id = await _seed_session(db_session)
    res = await db_session.execute(
        text(
            "INSERT INTO pipeline_revisions "
            "(session_id, ir_version, ir_jsonb, ir_sha256, state, created_by) "
            "VALUES (:s, 'v1', '{}'::jsonb, 'a', 'approved_for_execution', 'agent') "
            "RETURNING id"
        ),
        {"s": sess_id},
    )
    rev_id = res.scalar_one()
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text("INSERT INTO import_runs (revision_id, status) VALUES (:r, 'pondering')"),
            {"r": rev_id},
        )
        await db_session.flush()


async def test_import_run_tables_load_mode_check_rejects_invalid(db_session) -> None:
    _, sess_id = await _seed_session(db_session)
    res = await db_session.execute(
        text(
            "INSERT INTO pipeline_revisions "
            "(session_id, ir_version, ir_jsonb, ir_sha256, state, created_by) "
            "VALUES (:s, 'v1', '{}'::jsonb, 'a', 'approved_for_execution', 'agent') "
            "RETURNING id"
        ),
        {"s": sess_id},
    )
    rev_id = res.scalar_one()
    res = await db_session.execute(
        text("INSERT INTO import_runs (revision_id) VALUES (:r) RETURNING id"),
        {"r": rev_id},
    )
    run_id = res.scalar_one()
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO import_run_tables (run_id, table_name, load_mode) "
                "VALUES (:r, 'foo', 'sneakymode')"
            ),
            {"r": run_id},
        )
        await db_session.flush()


# --- Downgrade round-trip on a dedicated database -------------------------------


def test_downgrade_and_reupgrade_round_trip() -> None:
    """`alembic downgrade base` drops every §4 table; the managed user schema
    is intentionally preserved (it may hold loaded user data). A second
    `alembic upgrade head` succeeds against the cleaned DB."""
    db_name = f"structai_test_mig_{uuid.uuid4().hex[:8]}"
    sync_url = (
        f"postgresql+psycopg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{db_name}"
    )
    simple_url = (
        f"postgresql://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{db_name}"
    )

    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{db_name}"')

    try:
        prior = os.environ.get("DATABASE_URL_SYNC", "")
        os.environ["DATABASE_URL_SYNC"] = sync_url
        try:
            cfg = Config("alembic.ini")
            command.upgrade(cfg, "head")

            with psycopg.connect(simple_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_tables WHERE tablename = 'jobs'")
                    assert cur.fetchone() is not None
                    cur.execute(
                        "SELECT 1 FROM pg_namespace WHERE nspname = 'structai_user'"
                    )
                    assert cur.fetchone() is not None

            command.downgrade(cfg, "base")

            with psycopg.connect(simple_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    for t in EXPECTED_TABLES:
                        cur.execute(
                            "SELECT 1 FROM pg_tables WHERE tablename = %s", (t,)
                        )
                        assert cur.fetchone() is None, f"{t} still present"
                    cur.execute(
                        "SELECT 1 FROM pg_namespace WHERE nspname = 'structai_user'"
                    )
                    assert cur.fetchone() is not None, "managed schema must persist"

            command.upgrade(cfg, "head")
            with psycopg.connect(simple_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_tables WHERE tablename = 'jobs'")
                    assert cur.fetchone() is not None
        finally:
            os.environ["DATABASE_URL_SYNC"] = prior
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
