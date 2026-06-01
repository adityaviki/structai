from __future__ import annotations

from typing import TYPE_CHECKING

from ..settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


def workspace_root() -> Path:
    root = get_settings().workspace
    root.mkdir(parents=True, exist_ok=True)
    (root / "documents").mkdir(exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    return root


def document_dir(doc_id: str) -> Path:
    d = workspace_root() / "documents" / doc_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_dir(run_id: str) -> Path:
    d = workspace_root() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def write_document(
    doc_id: str,
    filename: str,
    chunks: AsyncIterator[bytes],
) -> tuple[Path, int]:
    """Stream-write an uploaded file. Returns (path, byte_count)."""

    out_path = document_dir(doc_id) / filename
    total = 0
    with out_path.open("wb") as fp:
        async for chunk in chunks:
            fp.write(chunk)
            total += len(chunk)
    return out_path, total
