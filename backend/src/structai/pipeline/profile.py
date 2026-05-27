"""Stage 1: profile a document into a structured ``DocumentProfile``.

A document can have one or more *regions* (think of them as table
candidates):

- CSV / TSV: one region named "default".
- XLSX: one region per sheet.
- JSON: depends on shape — array-of-objects is one region; object whose
  values are arrays is one region per key; NDJSON is one region named
  "default".

The output is the structured context the ``generate`` stage feeds to the
LLM along with project schema context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 -- used at runtime in helper signatures
from typing import Any

import polars as pl

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ColumnProfile:
    name: str
    inferred_type: str
    null_rate: float
    distinct_count: int | None
    samples: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "inferred_type": self.inferred_type,
            "null_rate": self.null_rate,
            "distinct_count": self.distinct_count,
            "samples": self.samples,
        }


@dataclass(slots=True)
class RegionProfile:
    name: str
    row_count: int
    columns: list[ColumnProfile]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "columns": [c.to_dict() for c in self.columns],
        }


@dataclass(slots=True)
class DocumentProfile:
    path: str
    filename: str
    size_bytes: int
    format: str  # csv | tsv | xlsx | json
    encoding: str
    regions: list[RegionProfile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "format": self.format,
            "encoding": self.encoding,
            "regions": [r.to_dict() for r in self.regions],
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Shared column profiling
# ---------------------------------------------------------------------------


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


def _profile_dataframe(name: str, df: pl.DataFrame) -> RegionProfile:
    total = df.height
    columns: list[ColumnProfile] = []
    for col_name, dtype in zip(df.columns, df.dtypes, strict=True):
        col = df[col_name]
        null_count = col.null_count()
        null_rate = (null_count / total) if total else 0.0
        try:
            distinct = col.n_unique()
        except pl.exceptions.PolarsError:
            distinct = None

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
                name=col_name,
                inferred_type=_polars_type_to_name(dtype),
                null_rate=round(null_rate, 4),
                distinct_count=distinct,
                samples=samples,
            )
        )

    return RegionProfile(name=name, row_count=total, columns=columns)


# ---------------------------------------------------------------------------
# Per-format profilers
# ---------------------------------------------------------------------------


def _profile_csv_like(path: Path, *, separator: str, fmt: str) -> DocumentProfile:
    try:
        df = pl.read_csv(
            path,
            separator=separator,
            infer_schema_length=10_000,
            try_parse_dates=True,
            ignore_errors=False,
        )
    except pl.exceptions.ComputeError as exc:
        msg = str(exc).lower()
        if "utf" in msg or "invalid utf" in msg:
            raise ValueError(
                f"{path.name!r} is not UTF-8. If you exported it from Excel, "
                "re-export as 'CSV UTF-8 (Comma delimited) (*.csv)' — the plain "
                "'CSV (Comma delimited)' option uses the OS ANSI codepage and "
                "can't represent non-Latin characters reliably."
            ) from exc
        raise

    region = _profile_dataframe("default", df)
    return DocumentProfile(
        path=str(path),
        filename=path.name,
        size_bytes=path.stat().st_size,
        format=fmt,
        encoding="utf8",
        regions=[region],
    )


def profile_csv(path: Path) -> DocumentProfile:
    return _profile_csv_like(path, separator=",", fmt="csv")


def profile_tsv(path: Path) -> DocumentProfile:
    return _profile_csv_like(path, separator="\t", fmt="tsv")


def profile_xlsx(path: Path) -> DocumentProfile:
    """One region per sheet."""

    sheets = pl.read_excel(path, sheet_id=0)
    # polars returns dict[str, DataFrame] when sheet_id=0 (== read all sheets).
    if not isinstance(sheets, dict):
        sheets = {"Sheet1": sheets}

    regions = [
        _profile_dataframe(name, df)
        for name, df in sheets.items()
        if df.height > 0 or len(df.columns) > 0
    ]
    notes: list[str] = []
    if not regions:
        notes.append("XLSX file contains no non-empty sheets.")

    return DocumentProfile(
        path=str(path),
        filename=path.name,
        size_bytes=path.stat().st_size,
        format="xlsx",
        encoding="utf-8",
        regions=regions,
        notes=notes,
    )


def _looks_like_array_of_objects(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, dict) for item in value[: min(10, len(value))])
    )


def _looks_like_object_of_arrays(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and len(value) > 0
        and all(_looks_like_array_of_objects(v) for v in value.values())
    )


def profile_json(path: Path) -> DocumentProfile:
    """Three shapes supported:

    1. **Array of objects**: ``[{...}, {...}, ...]`` → one region "default".
    2. **Object of arrays of objects**: ``{"users": [...], "orders": [...]}``
       → one region per top-level key.
    3. **NDJSON** (newline-delimited objects): one region "default".
    """

    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()

    regions: list[RegionProfile] = []
    notes: list[str] = []

    # Try the whole-file JSON path first.
    parsed: Any = None
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None

    if _looks_like_array_of_objects(parsed):
        df = pl.from_dicts(parsed)
        regions.append(_profile_dataframe("default", df))
    elif _looks_like_object_of_arrays(parsed):
        for key, val in parsed.items():
            df = pl.from_dicts(val)
            regions.append(_profile_dataframe(key, df))
    else:
        # Try NDJSON (one JSON object per line).
        try:
            df = pl.read_ndjson(path)
            if df.height > 0:
                regions.append(_profile_dataframe("default", df))
            else:
                notes.append("Could not parse JSON as array-of-objects, object-of-arrays, or NDJSON.")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"JSON parse failed: {exc!s}")

    return DocumentProfile(
        path=str(path),
        filename=path.name,
        size_bytes=path.stat().st_size,
        format="json",
        encoding="utf-8",
        regions=regions,
        notes=notes,
    )


def profile_document(path: Path, ext: str) -> DocumentProfile:
    ext = ext.lower()
    if ext == "csv":
        return profile_csv(path)
    if ext == "tsv":
        return profile_tsv(path)
    if ext == "xlsx":
        return profile_xlsx(path)
    if ext == "json":
        return profile_json(path)
    raise ValueError(f"profile: unsupported extension {ext!r}")
