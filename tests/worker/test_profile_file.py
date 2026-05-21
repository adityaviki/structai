"""Worker `profile_file` task tests (CHECKLIST.md line 142).

Exercises the task in isolation by calling it directly with a real
file row in the DB and a real CSV on disk. End-to-end coverage through
the worker's main loop lands in `test_cancellation_integration.py` and
already-existing `test_main_loop.py` patterns."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.config import Settings
from structai_core.db.models import File
from structai_core.jobs import CancellationToken, TerminalError

# Side-effect import: registers profile_file in the worker's dispatch
# registry. We use the task function directly (not via dispatch).
from structai_worker.tasks_profile import profile_file_task

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "csv"


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("STRUCTAI_DATA_DIR", str(tmp_path / "data"))
    return Settings()


async def _stage_file(
    db_session: AsyncSession, fixture_name: str, settings: Settings
) -> File:
    """Copy a fixture into the configured live directory and insert a
    matching `files` row."""
    src = FIXTURE_DIR / fixture_name
    live_dir = settings.data_dir / "uploads" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)

    contents = src.read_bytes()
    sha = hashlib.sha256(contents).hexdigest()
    live_path = live_dir / f"{sha}{src.suffix}"
    shutil.copy(src, live_path)

    file = File(
        original_name=fixture_name,
        bytes=len(contents),
        source_sha256=sha,
        quarantine_path=None,
        live_path=str(live_path),
    )
    db_session.add(file)
    await db_session.commit()
    await db_session.refresh(file)
    return file


# --- Happy path ----------------------------------------------------------


async def test_profile_file_writes_profiles_row_and_raw_artifact(
    db_session: AsyncSession, settings: Settings
) -> None:
    file = await _stage_file(db_session, "bom.csv", settings)
    payload = {"file_id": file.id, "profile_version": "v1"}
    token = CancellationToken()

    await profile_file_task(db_session, payload, token)

    rows = (
        await db_session.execute(
            text(
                "SELECT id, profile_sha256, profile_jsonb FROM profiles "
                "WHERE file_id = :fid"
            ),
            {"fid": file.id},
        )
    ).mappings().all()
    assert len(rows) == 1
    row = rows[0]
    assert len(row["profile_sha256"]) == 64
    assert row["profile_jsonb"]["row_count"] == 3

    # Raw artifact on disk.
    artifact = (
        settings.data_dir / "profiles" / f"{row['profile_sha256']}.raw.json"
    )
    assert artifact.exists()
    raw = json.loads(artifact.read_text())
    assert raw["row_count"] == 3


async def test_profile_file_idempotent_on_existing_profile(
    db_session: AsyncSession, settings: Settings
) -> None:
    file = await _stage_file(db_session, "bom.csv", settings)
    payload = {"file_id": file.id, "profile_version": "v1"}
    token = CancellationToken()

    await profile_file_task(db_session, payload, token)
    await profile_file_task(db_session, payload, token)  # second run no-ops

    n = (
        await db_session.execute(
            text("SELECT count(*) FROM profiles WHERE file_id = :fid"),
            {"fid": file.id},
        )
    ).scalar()
    assert n == 1


async def test_profile_file_redacts_pii_in_jsonb_keeps_raw_artifact(
    db_session: AsyncSession, settings: Settings
) -> None:
    """The PII emails fixture should produce a redacted JSONB
    (`<EMAIL_N>` placeholders) AND a raw on-disk artifact with the real
    email addresses."""
    file = await _stage_file(db_session, "pii/emails.csv", settings)
    payload = {"file_id": file.id, "profile_version": "v1"}
    token = CancellationToken()

    await profile_file_task(db_session, payload, token)

    row = (
        await db_session.execute(
            text("SELECT profile_sha256, profile_jsonb FROM profiles WHERE file_id = :fid"),
            {"fid": file.id},
        )
    ).mappings().one()

    redacted_email_col = next(c for c in row["profile_jsonb"]["columns"] if c["name"] == "email")
    assert all(str(v).startswith("<EMAIL_") for v in redacted_email_col["sample_values"])

    artifact = settings.data_dir / "profiles" / f"{row['profile_sha256']}.raw.json"
    raw = json.loads(artifact.read_text())
    raw_email_col = next(c for c in raw["columns"] if c["name"] == "email")
    assert any("@" in str(v) for v in raw_email_col["sample_values"])


# --- Error paths --------------------------------------------------------


async def test_profile_file_missing_file_id_is_terminal(
    db_session: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(TerminalError):
        await profile_file_task(
            db_session, {"profile_version": "v1"}, CancellationToken()
        )


async def test_profile_file_missing_file_row_is_terminal(
    db_session: AsyncSession, settings: Settings
) -> None:
    with pytest.raises(TerminalError, match="not found"):
        await profile_file_task(
            db_session, {"file_id": 999, "profile_version": "v1"}, CancellationToken()
        )


async def test_profile_file_missing_live_file_is_terminal(
    db_session: AsyncSession, settings: Settings
) -> None:
    """File row exists but the live file is gone (manual cleanup, etc)."""
    db_session.add(
        File(
            original_name="missing.csv",
            bytes=100,
            source_sha256="d" * 64,
            quarantine_path=None,
            live_path="/tmp/does_not_exist_structai.csv",
        )
    )
    await db_session.commit()
    f = (
        await db_session.execute(text("SELECT id FROM files WHERE source_sha256 = :s"), {"s": "d" * 64})
    ).scalar()

    with pytest.raises(TerminalError, match="live file missing"):
        await profile_file_task(
            db_session,
            {"file_id": f, "profile_version": "v1"},
            CancellationToken(),
        )
