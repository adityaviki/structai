"""Public entrypoint for the deterministic profile (plan §5).

`profile_file(path, ...)` orchestrates everything else under
`structai_core.profile`:

    sniffed Reader → identifier sanitization → per-column compute
      → assemble raw + redacted FileProfiles → apply truncation
      → compute profile_sha256 from the redacted artifact

The redacted artifact is the LLM-bound one (stored in
`profiles.profile_jsonb`); the raw artifact lives on disk under
`./data/profiles/<profile_sha256>.raw.json`. Both share the same
`profile_sha256` so a consumer can pair them.

Polars work happens via `asyncio.to_thread` so the event loop stays
free — the cancellation token (set by the worker's heartbeat) is
checked between columns and raises `JobCancelled` mid-loop on cancel.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import polars as pl

from structai_core.config import Settings
from structai_core.io.readers import open_reader
from structai_core.io.sniff import SniffResult
from structai_core.jobs import CancellationToken
from structai_core.profile import pii
from structai_core.profile.columns import profile_column
from structai_core.profile.models import (
    FileProfile,
    PROFILE_VERSION,
    ProfileResult,
)
from structai_core.profile.truncation import apply_truncation
from structai_core.schema.identifiers import sanitize_columns


async def profile_file(
    path: Path,
    *,
    sniff: SniffResult,
    source_sha256: str,
    profile_version: str = PROFILE_VERSION,
    token: CancellationToken,
    settings: Settings,
) -> ProfileResult:
    """Async wrapper around the synchronous Polars pipeline. Cancellation
    works because `profile_column` calls `token.raise_if_cancelled()`
    between columns; the in-thread `JobCancelled` propagates back."""

    return await asyncio.to_thread(
        _profile_file_sync,
        path,
        sniff,
        source_sha256,
        profile_version,
        token,
        settings,
    )


def _profile_file_sync(
    path: Path,
    sniff: SniffResult,
    source_sha256: str,
    profile_version: str,
    token: CancellationToken,
    settings: Settings,
) -> ProfileResult:
    reader = open_reader(path, sniff)
    df = reader.read_all()
    total_rows = df.height
    duplicate_row_count = _duplicate_row_count(df)
    raw_to_safe = sanitize_columns(list(df.columns))

    raw_columns = []
    for position, raw_name in enumerate(df.columns):
        safe_name = raw_to_safe[raw_name]
        series = df.get_column(raw_name)
        col = profile_column(
            series,
            raw_name=raw_name,
            safe_name=safe_name,
            position=position,
            total_rows=total_rows,
            token=token,
        )
        raw_columns.append(col)

    redacted_columns = [
        pii.redact_column(col, allow_raw=settings.allow_raw_llm_samples)
        for col in raw_columns
    ]

    base_kwargs = dict(
        row_count=total_rows,
        duplicate_row_count=duplicate_row_count,
        encoding=sniff.encoding,
        delimiter=sniff.delimiter,
        has_header=sniff.has_header,
        source_sha256=source_sha256,
        profile_sha256="",  # filled in below
        profile_version=profile_version,
        raw_to_safe=raw_to_safe,
    )

    raw_profile = apply_truncation(FileProfile(**base_kwargs, columns=raw_columns))
    redacted_profile = apply_truncation(
        FileProfile(**base_kwargs, columns=redacted_columns)
    )

    profile_sha = _compute_profile_sha(redacted_profile)
    raw_profile.profile_sha256 = profile_sha
    redacted_profile.profile_sha256 = profile_sha

    return ProfileResult(raw=raw_profile, redacted=redacted_profile)


def _duplicate_row_count(df: pl.DataFrame) -> int:
    """Number of rows that appear more than once. A pair of identical
    rows contributes 2 to this count (matches the natural
    interpretation: 'how many of the rows are duplicates of something
    else?')."""
    if df.height == 0:
        return 0
    return int(df.is_duplicated().sum())


def _compute_profile_sha(profile: FileProfile) -> str:
    payload = json.dumps(
        profile.model_dump(mode="json", exclude={"profile_sha256"}),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
