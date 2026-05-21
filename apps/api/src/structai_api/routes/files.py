"""File upload + profile fetch routes (plan §10 Phase 1).

`POST /files` accepts a multipart upload, streams it to a quarantine
file under `data_dir/uploads/quarantine/` while hashing, atomically
renames to `data_dir/uploads/live/<sha>.<ext>` once sniffed, inserts a
`files` row, and enqueues a `profile_file` job. Dedup by
`source_sha256` returns 200 + the existing row instead of duplicating
the upload.

`GET /files` joins `files` with `profiles` and the latest
`profile_file` job to derive a UI-friendly status
(`queued`/`profiling`/`profiled`/`failed`).

`GET /files/:id/profile` returns the latest profile JSONB validated
against the `FileProfile` shape (or 404).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from structai_api.deps import get_session, get_settings
from structai_core.config import Settings
from structai_core.db.models import File
from structai_core.io.sniff import SniffError, sniff
from structai_core.jobs.queue import enqueue
from structai_core.profile.models import FileProfile, PROFILE_VERSION

router = APIRouter(prefix="/files", tags=["files"])

_ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
_CHUNK_BYTES = 1024 * 1024  # 1 MB


class FileStatus(str, Enum):
    queued = "queued"
    profiling = "profiling"
    profiled = "profiled"
    failed = "failed"


class FileSummary(BaseModel):
    id: int
    original_name: str
    bytes: int
    source_sha256: str
    uploaded_at: datetime
    status: FileStatus
    profile_id: int | None = None


class FileListResponse(BaseModel):
    items: list[FileSummary]


@router.post("", response_model=FileSummary)
async def upload_file(
    file: UploadFile,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileSummary:
    """Multipart upload. Streams to a quarantine temp file, hashes,
    atomically renames to the live area, then enqueues profiling."""

    original_name = file.filename or "unnamed"
    ext = Path(original_name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file extension: {ext!r}",
        )

    quarantine_dir = settings.data_dir / "uploads" / "quarantine"
    live_dir = settings.data_dir / "uploads" / "live"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    size = 0
    tmp = tempfile.NamedTemporaryFile(
        dir=str(quarantine_dir), delete=False, suffix=ext
    )
    quarantine_path = Path(tmp.name)
    try:
        while True:
            chunk = await file.read(_CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_bytes:
                tmp.close()
                quarantine_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"upload exceeds max_upload_bytes ({settings.max_upload_bytes})",
                )
            hasher.update(chunk)
            tmp.write(chunk)
        tmp.close()
    except HTTPException:
        raise
    except Exception:
        tmp.close()
        quarantine_path.unlink(missing_ok=True)
        raise

    source_sha = hasher.hexdigest()

    existing = (
        await session.execute(select(File).where(File.source_sha256 == source_sha))
    ).scalar_one_or_none()
    if existing is not None:
        quarantine_path.unlink(missing_ok=True)
        response.status_code = 200
        return await _summary_for(session, existing)

    try:
        sniff(quarantine_path)
    except SniffError as exc:
        quarantine_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail=f"could not sniff file: {exc}",
        ) from exc

    live_path = live_dir / f"{source_sha}{ext}"
    os.rename(quarantine_path, live_path)

    new_file = File(
        original_name=original_name,
        bytes=size,
        source_sha256=source_sha,
        quarantine_path=None,
        live_path=str(live_path),
        retention_until=datetime.now(UTC) + timedelta(days=settings.retention_days),
    )
    session.add(new_file)
    await session.flush()
    assert new_file.id is not None

    await enqueue(
        session,
        kind="profile_file",
        payload={"file_id": new_file.id, "profile_version": PROFILE_VERSION},
        idempotency_key=f"profile_file:{source_sha}:{PROFILE_VERSION}",
    )
    await session.commit()
    response.status_code = 201
    return await _summary_for(session, new_file)


@router.get("", response_model=FileListResponse)
async def list_files(
    session: AsyncSession = Depends(get_session),
) -> FileListResponse:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    f.id AS id,
                    f.original_name AS original_name,
                    f.bytes AS bytes,
                    f.source_sha256 AS source_sha256,
                    f.uploaded_at AS uploaded_at,
                    p.id AS profile_id,
                    (
                        SELECT j.status FROM jobs j
                        WHERE j.kind = 'profile_file'
                          AND (j.payload_jsonb->>'file_id')::bigint = f.id
                        ORDER BY j.created_at DESC
                        LIMIT 1
                    ) AS job_status
                FROM files f
                LEFT JOIN profiles p ON p.file_id = f.id
                ORDER BY f.uploaded_at DESC, f.id DESC
                """
            )
        )
    ).mappings().all()

    items = [
        FileSummary(
            id=row["id"],
            original_name=row["original_name"],
            bytes=row["bytes"],
            source_sha256=row["source_sha256"],
            uploaded_at=row["uploaded_at"],
            status=_derive_status(row["profile_id"], row["job_status"]),
            profile_id=row["profile_id"],
        )
        for row in rows
    ]
    return FileListResponse(items=items)


@router.get("/{file_id}/profile", response_model=FileProfile)
async def get_profile(
    file_id: int,
    session: AsyncSession = Depends(get_session),
) -> FileProfile:
    row = (
        await session.execute(
            text(
                """
                SELECT profile_jsonb
                FROM profiles
                WHERE file_id = :fid
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"fid": file_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"no profile for file_id {file_id}",
        )
    return FileProfile.model_validate(row["profile_jsonb"])


# --- Helpers --------------------------------------------------------------


def _derive_status(profile_id: int | None, job_status: str | None) -> FileStatus:
    if profile_id is not None:
        return FileStatus.profiled
    if job_status == "running":
        return FileStatus.profiling
    if job_status == "failed":
        return FileStatus.failed
    return FileStatus.queued


async def _summary_for(session: AsyncSession, file: File) -> FileSummary:
    row = (
        await session.execute(
            text(
                """
                SELECT p.id AS profile_id,
                       (
                           SELECT j.status FROM jobs j
                           WHERE j.kind = 'profile_file'
                             AND (j.payload_jsonb->>'file_id')::bigint = :fid
                           ORDER BY j.created_at DESC
                           LIMIT 1
                       ) AS job_status
                FROM files f
                LEFT JOIN profiles p ON p.file_id = f.id
                WHERE f.id = :fid
                """
            ),
            {"fid": file.id},
        )
    ).mappings().one_or_none()
    profile_id = row["profile_id"] if row else None
    job_status = row["job_status"] if row else None
    return FileSummary(
        id=file.id,
        original_name=file.original_name,
        bytes=file.bytes,
        source_sha256=file.source_sha256,
        uploaded_at=file.uploaded_at,
        status=_derive_status(profile_id, job_status),
        profile_id=profile_id,
    )
