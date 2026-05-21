"""Pydantic models for the deterministic profile (plan §5 lines 148-186).

Single source of truth for the profile JSON shape: used for both the
redacted artifact (stored in `profiles.profile_jsonb`) and the raw
artifact (`./data/profiles/<profile_sha256>.raw.json`), and as the
response type for `GET /files/:id/profile` so the OpenAPI codegen
carries the shape to TypeScript.

Bump `PROFILE_VERSION` only on schema-breaking changes — the worker
allocates one row per `(file_id, profile_version)` and the agent uses
the version to invalidate cached profiles.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

PROFILE_VERSION = "v1"


class InferredType(str, Enum):
    int = "int"
    float = "float"
    bool = "bool"
    date = "date"
    datetime = "datetime"
    string = "string"
    enum = "enum"
    json = "json"


class CardinalityClass(str, Enum):
    unique = "unique"
    low = "low"
    high = "high"


class PiiClass(str, Enum):
    """High-confidence + best-effort classes. `name_like` / `address_like`
    are heuristics — they populate `pii_warnings`, never `pii_class`."""

    none = "none"
    email = "email"
    phone = "phone"
    ip = "ip"
    national_id = "national_id"
    cc_like = "cc_like"


class TopKEntry(BaseModel):
    value: str | int | float | bool | None
    count: int


class LengthStats(BaseModel):
    min: int
    max: int
    p50: int
    p99: int


class Quantiles(BaseModel):
    p1: Any | None = None
    p50: Any | None = None
    p99: Any | None = None


class ColumnProfile(BaseModel):
    name: str
    safe_name: str
    position: int
    inferred_type: InferredType
    null_count: int
    null_rate: float
    empty_string_count: int = 0
    distinct_count: int
    cardinality_class: CardinalityClass
    min: Any | None = None
    max: Any | None = None
    quantiles: Quantiles | None = None
    sample_values: list[Any] = Field(default_factory=list)
    top_k: list[TopKEntry] | None = None
    length_stats: LengthStats | None = None
    pattern_hits: dict[str, float] = Field(default_factory=dict)
    pii_class: PiiClass = PiiClass.none
    pii_warnings: list[str] = Field(default_factory=list)
    date_format_candidates: dict[str, float] | None = None
    leading_zero_ratio: float | None = None
    decimal_separator: str | None = None
    thousands_separator: str | None = None
    currency_symbol: str | None = None
    percent_unit: bool = False
    unit_hint: str | None = None
    timezone_hints: dict[str, Any] | None = None
    outlier_examples: list[Any] = Field(default_factory=list)
    pk_score: float
    fk_score: float | None = None
    truncated: bool = False


class OmittedColumn(BaseModel):
    name: str
    safe_name: str
    position: int
    inferred_type: InferredType
    null_rate: float
    distinct_count: int
    pk_score: float
    reason: str


class FileProfile(BaseModel):
    row_count: int
    duplicate_row_count: int
    encoding: str
    delimiter: str
    has_header: bool
    source_sha256: str
    profile_sha256: str
    profile_version: str = PROFILE_VERSION
    raw_to_safe: dict[str, str]
    columns: list[ColumnProfile]
    omitted_columns: list[OmittedColumn] = Field(default_factory=list)


class ProfileResult(BaseModel):
    """The pair the profile runner returns. `redacted` lands in JSONB;
    `raw` is written next to the file under `./data/profiles/`."""

    raw: FileProfile
    redacted: FileProfile
