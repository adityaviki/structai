"""SQLAlchemy model round-trip + FK cascade behaviour."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from structai_core.db.models import (
    AGENT_SESSION_STATUSES,
    PIPELINE_ARTIFACT_KINDS,
    PIPELINE_REVISION_CREATED_BY,
    PIPELINE_REVISION_STATES,
    AgentSession,
    File,
    PipelineArtifact,
    PipelineRevision,
    Profile,
)


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


async def _seed_session(db_session, marker: str) -> AgentSession:
    file = File(original_name="x.csv", bytes=1, source_sha256=_h(f"file-{marker}"))
    db_session.add(file)
    await db_session.flush()
    sess = AgentSession(file_id=file.id)
    db_session.add(sess)
    await db_session.flush()
    return sess


@pytest.mark.parametrize("state", PIPELINE_REVISION_STATES)
async def test_pipeline_revision_accepts_each_state(db_session, state: str) -> None:
    sess = await _seed_session(db_session, state)
    rev = PipelineRevision(
        session_id=sess.id,
        ir_version="2026-05-structai-v1",
        ir_jsonb={"ir_version": "2026-05-structai-v1", "tables": []},
        ir_sha256=_h(f"ir-{state}"),
        state=state,
        created_by="agent",
    )
    db_session.add(rev)
    await db_session.flush()
    assert rev.id is not None
    assert rev.state == state


@pytest.mark.parametrize("created_by", PIPELINE_REVISION_CREATED_BY)
async def test_pipeline_revision_accepts_each_created_by(
    db_session, created_by: str
) -> None:
    sess = await _seed_session(db_session, created_by)
    rev = PipelineRevision(
        session_id=sess.id,
        ir_version="v1",
        ir_jsonb={},
        ir_sha256=_h(f"cb-{created_by}"),
        state="proposed_ir",
        created_by=created_by,
    )
    db_session.add(rev)
    await db_session.flush()
    assert rev.created_by == created_by


@pytest.mark.parametrize("status", AGENT_SESSION_STATUSES)
async def test_agent_session_accepts_each_status(db_session, status: str) -> None:
    file = File(original_name="x.csv", bytes=1, source_sha256=_h(f"as-{status}"))
    db_session.add(file)
    await db_session.flush()
    sess = AgentSession(file_id=file.id, status=status)
    db_session.add(sess)
    await db_session.flush()
    assert sess.status == status


@pytest.mark.parametrize("kind", PIPELINE_ARTIFACT_KINDS)
async def test_pipeline_artifact_accepts_each_kind(db_session, kind: str) -> None:
    sess = await _seed_session(db_session, kind)
    rev = PipelineRevision(
        session_id=sess.id,
        ir_version="v1",
        ir_jsonb={},
        ir_sha256=_h(f"art-rev-{kind}"),
        state="proposed_ir",
        created_by="agent",
    )
    db_session.add(rev)
    await db_session.flush()
    art = PipelineArtifact(
        revision_id=rev.id, kind=kind, path="/p", sha256=_h(f"art-{kind}")
    )
    db_session.add(art)
    await db_session.flush()
    assert art.id is not None


async def test_ir_jsonb_round_trips(db_session) -> None:
    """`ir_jsonb` is the canonical IR persistence path (plan §4 invariant)."""
    sess = await _seed_session(db_session, "rt")
    ir = {
        "ir_version": "2026-05-structai-v1",
        "source": {"file_id": "abc", "reader": "csv"},
        "tables": [
            {"name": "customers", "load_mode": "upsert", "columns": [], "ops": []},
        ],
    }
    rev = PipelineRevision(
        session_id=sess.id,
        ir_version="2026-05-structai-v1",
        ir_jsonb=ir,
        ir_sha256=_h("rt"),
        state="proposed_ir",
        created_by="agent",
    )
    db_session.add(rev)
    await db_session.flush()
    await db_session.refresh(rev)
    assert rev.ir_jsonb == ir


async def test_deleting_file_cascades_through_full_chain(db_session) -> None:
    """files → profiles | agent_sessions → pipeline_revisions → pipeline_artifacts.

    All children must vanish when the parent file is deleted.
    """
    file = File(original_name="x.csv", bytes=10, source_sha256=_h("cascade"))
    db_session.add(file)
    await db_session.flush()

    db_session.add(
        Profile(file_id=file.id, profile_sha256=_h("p"), profile_jsonb={})
    )
    sess = AgentSession(file_id=file.id)
    db_session.add(sess)
    await db_session.flush()

    rev = PipelineRevision(
        session_id=sess.id,
        ir_version="v1",
        ir_jsonb={},
        ir_sha256=_h("rev"),
        state="proposed_ir",
        created_by="agent",
    )
    db_session.add(rev)
    await db_session.flush()
    db_session.add(
        PipelineArtifact(
            revision_id=rev.id, kind="pipeline_py", path="/p", sha256=_h("art")
        )
    )
    await db_session.flush()

    file_id, sess_id, rev_id = file.id, sess.id, rev.id

    await db_session.delete(file)
    await db_session.flush()

    assert (
        await db_session.execute(select(Profile).where(Profile.file_id == file_id))
    ).first() is None
    assert (
        await db_session.execute(
            select(AgentSession).where(AgentSession.id == sess_id)
        )
    ).first() is None
    assert (
        await db_session.execute(
            select(PipelineRevision).where(PipelineRevision.id == rev_id)
        )
    ).first() is None
    assert (
        await db_session.execute(
            select(PipelineArtifact).where(PipelineArtifact.revision_id == rev_id)
        )
    ).first() is None
