"""Stage 1: profile a document into a structured `FileProfile`.

Phase 1 handles CSV only. polars does the heavy lifting (sniffs delimiter,
type-infers, computes null rates). The output is what the `generate` stage
feeds into the LLM along with project schema context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class ColumnProfile:
    name: str
    inferred_type: str  # int|float|bool|date|datetime|string|null
    null_rate: float
    distinct_count: int | None
    samples: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FileProfile:
    path: str
    filename: str
    size_bytes: int
    total_rows: int
    delimiter: str
    encoding: str
    has_header: bool
    columns: list[ColumnProfile]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "total_rows": self.total_rows,
            "delimiter": self.delimiter,
            "encoding": self.encoding,
            "has_header": self.has_header,
            "columns": [c.to_dict() for c in self.columns],
        }


def _polars_type_to_name(dtype: pl.DataType) -> str:
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
        return "int"
    if dtype in (pl.Float32, pl.Float64):
        return "float"
    if dtype == pl.Boolean:
        return "bool"
    if dtype == pl.Date:
        return "date"
    if dtype in (pl.Datetime, pl.Time):
        return "datetime"
    if dtype == pl.Null:
        return "null"
    return "string"


def profile_csv(path: Path) -> FileProfile:
    """Profile a CSV file. Read once with type inference, then summarize."""

    # polars will sniff delimiter/encoding for CSV automatically.
    df = pl.read_csv(
        path,
        infer_schema_length=10_000,
        try_parse_dates=True,
        ignore_errors=False,
    )

    total = df.height
    columns: list[ColumnProfile] = []
    for name, dtype in zip(df.columns, df.dtypes, strict=True):
        col = df[name]
        null_count = col.null_count()
        null_rate = (null_count / total) if total else 0.0
        try:
            distinct = col.n_unique()
        except pl.exceptions.PolarsError:
            distinct = None

        # First few non-null distinct values as strings.
        samples: list[str] = []
        seen: set[str] = set()
        for v in col.drop_nulls().head(50).to_list():
            sv = str(v)
            if sv in seen:
                continue
            seen.add(sv)
            samples.append(sv)
            if len(samples) >= 5:
                break

        columns.append(
            ColumnProfile(
                name=name,
                inferred_type=_polars_type_to_name(dtype),
                null_rate=round(null_rate, 4),
                distinct_count=distinct,
                samples=samples,
            )
        )

    return FileProfile(
        path=str(path),
        filename=path.name,
        size_bytes=path.stat().st_size,
        total_rows=total,
        delimiter=",",  # polars sniffs internally; we don't surface it for Phase 1.
        encoding="utf-8",
        has_header=True,
        columns=columns,
    )


def profile_document(path: Path, ext: str) -> FileProfile:
    if ext == "csv":
        return profile_csv(path)
    raise ValueError(f"profile: unsupported extension {ext!r} for Phase 1")
