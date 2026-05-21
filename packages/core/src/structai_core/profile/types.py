"""Type inference + leading-zero / decimal-separator / currency / percent.

Operates on a sample of non-null string values from a Polars column
(everything reads as Utf8 — see `io.readers`). Returns a small
`TypeInferenceResult` that `profile.columns` copies into the
`ColumnProfile`.

Type-preservation rule (plan §5 line 174 / CHECKLIST.md line 87):
columns that look int-like but have leading zeros (`"00123"`) stay as
`string`. ZIP codes, SKUs, and account numbers don't become ints.

The decision threshold is 95% for int / 90% for float-shapes — a single
out-of-pattern value pulls the type down to `string`. Empty samples
default to `string`.
"""

from __future__ import annotations

import json
import re

import polars as pl
from pydantic import BaseModel

from structai_core.profile import patterns
from structai_core.profile.models import InferredType

_INT_RE = re.compile(r"^-?\d+$")
_PLAIN_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
_BOOL_TOKENS = frozenset({"true", "false", "yes", "no"})
_LEADING_ZERO_THRESHOLD = 0.05
_TYPE_THRESHOLD = 0.95
_FLOAT_THRESHOLD = 0.9


class TypeInferenceResult(BaseModel):
    inferred_type: InferredType
    leading_zero_ratio: float = 0.0
    decimal_separator: str | None = None
    thousands_separator: str | None = None
    currency_symbol: str | None = None
    percent_unit: bool = False
    unit_hint: str | None = None


def infer_type(
    values: pl.Series, *, name: str, sample_size: int = 1000
) -> TypeInferenceResult:
    sample = _string_sample(values, sample_size)
    if not sample:
        return TypeInferenceResult(inferred_type=InferredType.string)

    if _is_bool(sample):
        return TypeInferenceResult(inferred_type=InferredType.bool)

    # ---- int (with type-preservation) -----------------------------------
    int_hits = sum(1 for v in sample if _INT_RE.fullmatch(v.strip()) is not None)
    int_rate = int_hits / len(sample)
    leading_zero_ratio = (
        sum(1 for v in sample if _has_leading_zero(v.strip())) / len(sample)
    )
    if int_rate >= _TYPE_THRESHOLD:
        if leading_zero_ratio > _LEADING_ZERO_THRESHOLD:
            return TypeInferenceResult(
                inferred_type=InferredType.string,
                leading_zero_ratio=round(leading_zero_ratio, 3),
            )
        return TypeInferenceResult(
            inferred_type=InferredType.int,
            leading_zero_ratio=round(leading_zero_ratio, 3),
        )

    # ---- floats: German decimal -----------------------------------------
    gd_rate = _rate(sample, patterns.PATTERNS["german_decimal"])
    us_rate = _rate(sample, patterns.PATTERNS["us_decimal"])
    plain_rate = _rate(sample, _PLAIN_FLOAT_RE)

    if gd_rate >= _FLOAT_THRESHOLD and gd_rate >= us_rate:
        return TypeInferenceResult(
            inferred_type=InferredType.float,
            decimal_separator=",",
            thousands_separator=".",
        )
    if us_rate >= _FLOAT_THRESHOLD:
        return TypeInferenceResult(
            inferred_type=InferredType.float,
            decimal_separator=".",
            thousands_separator=",",
        )
    if plain_rate >= _FLOAT_THRESHOLD:
        return TypeInferenceResult(
            inferred_type=InferredType.float,
            decimal_separator=".",
        )

    # ---- currency / percent ---------------------------------------------
    cur_rate = _rate(sample, patterns.PATTERNS["currency_amount"])
    if cur_rate >= _FLOAT_THRESHOLD:
        symbol = _detect_currency_symbol(sample)
        return TypeInferenceResult(
            inferred_type=InferredType.float,
            currency_symbol=symbol,
            decimal_separator=".",
            thousands_separator=",",
        )

    pct_rate = _rate(sample, patterns.PATTERNS["percent"])
    if pct_rate >= _FLOAT_THRESHOLD:
        return TypeInferenceResult(
            inferred_type=InferredType.float,
            percent_unit=True,
        )

    # ---- dates / datetimes ----------------------------------------------
    candidates = patterns.date_format_candidates(values, sample_size=sample_size)
    if candidates:
        best_fmt, best_rate = next(iter(candidates.items()))
        if best_rate >= _FLOAT_THRESHOLD:
            has_time = any(t in best_fmt for t in ("%H", "%M", "%S"))
            return TypeInferenceResult(
                inferred_type=InferredType.datetime if has_time else InferredType.date
            )

    # ---- JSON ------------------------------------------------------------
    if all(_is_json_doc(v) for v in sample):
        return TypeInferenceResult(inferred_type=InferredType.json)

    return TypeInferenceResult(inferred_type=InferredType.string)


# --- Helpers --------------------------------------------------------------


def _string_sample(values: pl.Series, sample_size: int) -> list[str]:
    s = values.drop_nulls().cast(pl.Utf8, strict=False)
    if s.len() == 0:
        return []
    if s.len() > sample_size:
        s = s.sample(sample_size, seed=0)
    out: list[str] = []
    for v in s.to_list():
        if v is None:
            continue
        sv = str(v)
        if sv == "":
            continue
        out.append(sv)
    return out


def _rate(sample: list[str], pattern: re.Pattern[str]) -> float:
    if not sample:
        return 0.0
    hits = sum(1 for v in sample if pattern.fullmatch(v.strip()) is not None)
    return hits / len(sample)


def _is_bool(sample: list[str]) -> bool:
    lowered = {v.strip().lower() for v in sample}
    return lowered and lowered.issubset(_BOOL_TOKENS) and len(lowered) >= 2


def _has_leading_zero(value: str) -> bool:
    """`00123` yes; `0` no; `-00123` no (rare and out of scope for v1)."""
    return len(value) > 1 and value[0] == "0" and value[1:].isdigit()


def _detect_currency_symbol(sample: list[str]) -> str | None:
    for v in sample:
        v = v.strip()
        if v and v[0] in "$£€¥":
            return v[0]
    return None


def _is_json_doc(value: str) -> bool:
    v = value.strip()
    if not (v.startswith(("{", "[")) and v.endswith(("}", "]"))):
        return False
    try:
        json.loads(v)
        return True
    except (json.JSONDecodeError, ValueError):
        return False
