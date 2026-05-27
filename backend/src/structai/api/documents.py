from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, UploadFile

from ..db.ids import new_id
from ..db.pools import get_pools
from ..logging import log
from ..schemas.document import DocumentOut
from ..workspace.storage import document_dir
from .errors import ApiError

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/projects/{project_id}/documents", tags=["documents"])

ALLOWED_EXTS = {"csv", "tsv", "xlsx", "json"}


def _row_to_doc(row: asyncpg.Record) -> DocumentOut:
    return DocumentOut(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        ext=row["ext"],
        size_bytes=row["size_bytes"],
        status=row["status"],
        last_import_id=row["last_import_id"],
        uploaded_at=row["uploaded_at"],
    )


async def _project_exists(conn: asyncpg.Connection, project_id: str) -> bool:
    val = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", project_id)
    return val is not None


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(project_id: str, file: UploadFile) -> DocumentOut:
    pools = get_pools()
    meta = await pools.meta()

    async with meta.acquire() as conn:
        if not await _project_exists(conn, project_id):
            raise ApiError(
                status=404, title="Not found", detail=f"Project {project_id!r} not found."
            )

    original = Path(file.filename or "upload").name
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTS:
        raise ApiError(
            status=415,
            title="Unsupported file type",
            detail=f"Supported formats: {', '.join(sorted(ALLOWED_EXTS))} (got .{ext!r}).",
        )

    doc_id = new_id()
    out_path = document_dir(doc_id) / original

    total = 0
    # Stream-write in chunks; UploadFile.read(N) returns up to N bytes per call.
    with out_path.open("wb") as fp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            fp.write(chunk)
            total += len(chunk)

    storage_rel = str(out_path.relative_to(out_path.parents[2]))

    async with meta.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (id, project_id, name, ext, size_bytes, storage_path)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            doc_id,
            project_id,
            original,
            ext,
            total,
            storage_rel,
        )

    assert row is not None
    log.info("document.uploaded", id=doc_id, project_id=project_id, bytes=total)
    return _row_to_doc(row)


@router.delete("/{document_id}", status_code=204)
async def delete_document(project_id: str, document_id: str) -> None:
    import shutil

    from ..workspace.storage import document_dir

    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        doc = await conn.fetchrow(
            "SELECT * FROM documents WHERE id = $1 AND project_id = $2",
            document_id,
            project_id,
        )
        if doc is None:
            raise ApiError(
                status=404,
                title="Not found",
                detail=f"Document {document_id!r} not found.",
            )
        # Block delete if a non-final, non-reverted run still references it.
        blockers = await conn.fetchval(
            """
            SELECT COUNT(*) FROM import_runs
            WHERE document_id = $1
              AND status NOT IN ('failed','cancelled','reverted')
            """,
            document_id,
        )
        if blockers and blockers > 0:
            raise ApiError(
                status=409,
                title="In use",
                detail="This document is referenced by a run that hasn't been reverted, cancelled, or failed. Undo or cancel those imports first.",
            )
        await conn.execute("DELETE FROM documents WHERE id = $1", document_id)

    d = document_dir(document_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    log.info("document.deleted", id=document_id, project_id=project_id)


@router.get("", response_model=list[DocumentOut])
async def list_documents(project_id: str) -> list[DocumentOut]:
    pools = get_pools()
    meta = await pools.meta()
    async with meta.acquire() as conn:
        if not await _project_exists(conn, project_id):
            raise ApiError(
                status=404, title="Not found", detail=f"Project {project_id!r} not found."
            )
        rows = await conn.fetch(
            "SELECT * FROM documents WHERE project_id = $1 ORDER BY uploaded_at DESC",
            project_id,
        )
    return [_row_to_doc(r) for r in rows]
