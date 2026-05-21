"""Regex bank + date-format candidates + timezone hints.

Used by `profile.columns` to populate `pattern_hits`,
`date_format_candidates`, and `timezone_hints` per column (plan §5
lines 161, 163, 167; CHECKLIST.md lines 88-90).

Hit rates are computed against a deterministic sample of non-null
values per column. Patterns below a 5% hit rate are dropped from the
output; date formats below 10% likewise. The `cc_luhn_format` regex is
format-only (16 digits) — Luhn validation lives in `profile.pii`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import polars as pl

# --- Regex bank ------------------------------------------------------------

PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"),
    "phone_e164": re.compile(r"^\+[1-9]\d{6,14}$"),
    "phone_us": re.compile(
        r"^(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$"
    ),
    "ip_v4": re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)$"
    ),
    "ip_v6": re.compile(r"^(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}$"),
    "iso_date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "iso_datetime": re.compile(
        r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:?\d{2})?$"
    ),
    "uuid": re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    "url": re.compile(r"^https?://[A-Za-z0-9.\-]+(?:[:/?#][^\s]*)?$"),
    "currency_amount": re.compile(r"^[\$£€¥]\s?-?\d[\d.,]*$"),
    "percent": re.compile(r"^-?\d+(?:[.,]\d+)?\s?%$"),
    "german_decimal": re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d+$"),
    "us_decimal": re.compile(r"^-?\d{1,3}(?:,\d{3})+(?:\.\d+)?$"),
    "numeric_id": re.compile(r"^\d{4,}$"),
    "national_id_us_ssn": re.compile(r"^\d{3}-\d{2}-\d{4}$"),
    "cc_luhn_format": re.compile(r"^(?:\d[ \-]?){13,19}\d$"),
}


def pattern_hits(
    values: pl.Series, *, sample_size: int = 1000, min_hit_rate: float = 0.05
) -> dict[str, float]:
    """Returns `{pattern_name: hit_rate}` for every regex with a hit rate
    strictly above `min_hit_rate`."""
    sample = _string_sample(values, sample_size)
    if not sample:
        return {}
    total = len(sample)
    result: dict[str, float] = {}
    for name, pattern in PATTERNS.items():
        hits = sum(1 for v in sample if pattern.fullmatch(v) is not None)
        rate = hits / total
        if rate > min_hit_rate:
            result[name] = round(rate, 3)
    return result


# --- Date format candidates -----------------------------------------------

DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y",
)


def date_format_candidates(
    values: pl.Series, *, sample_size: int = 1000, min_hit_rate: float = 0.1
) -> dict[str, float]:
    """Returns `{format_string: success_rate}` for each `strptime`
    format with a rate strictly above `min_hit_rate`. Sorted descending."""
    sample = _string_sample(values, sample_size)
    if not sample:
        return {}
    total = len(sample)
    candidates: list[tuple[str, float]] = []
    for fmt in DATE_FORMATS:
        hits = 0
        for v in sample:
            try:
                datetime.strptime(v, fmt)
                hits += 1
            except ValueError:
                continue
        rate = hits / total
        if rate > min_hit_rate:
            candidates.append((fmt, round(rate, 3)))
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return dict(candidates)


# --- Timezone hints --------------------------------------------------------

_TZ_OFFSET = re.compile(r"(Z|[+\-]\d{2}:?\d{2})$")


def timezone_hints(
    values: pl.Series, *, sample_size: int = 1000, min_datetime_rate: float = 0.5
) -> dict[str, Any] | None:
    """Returns `{"offsets": [...], "naive_ratio": float}` when at least
    `min_datetime_rate` of the sample looks like an ISO datetime; else
    None."""
    sample = _string_sample(values, sample_size)
    if not sample:
        return None
    datetime_hits = sum(
        1 for v in sample if PATTERNS["iso_datetime"].fullmatch(v) is not None
    )
    if datetime_hits / len(sample) < min_datetime_rate:
        return None

    offsets: set[str] = set()
    naive = 0
    for v in sample:
        if PATTERNS["iso_datetime"].fullmatch(v) is None:
            continue
        m = _TZ_OFFSET.search(v)
        if m is None:
            naive += 1
        else:
            tz = m.group(1)
            # Normalize "+0530" → "+05:30" for stable output.
            if tz != "Z" and ":" not in tz:
                tz = f"{tz[:3]}:{tz[3:]}"
            offsets.add(tz)

    return {
        "offsets": sorted(offsets),
        "naive_ratio": round(naive / datetime_hits, 3),
    }


# --- Helpers --------------------------------------------------------------


def _string_sample(values: pl.Series, sample_size: int) -> list[str]:
    """Drop nulls, materialize as Python strings, deterministic sample."""
    s = values.drop_nulls().cast(pl.Utf8, strict=False)
    if s.len() == 0:
        return []
    if s.len() > sample_size:
        s = s.sample(sample_size, seed=0)
    return [v for v in s.to_list() if v is not None and v != ""]
