"""Pattern bank + date-format candidate tests (CHECKLIST.md line 136)."""

from __future__ import annotations

import polars as pl
import pytest

from structai_core.profile.patterns import (
    PATTERNS,
    date_format_candidates,
    pattern_hits,
    timezone_hints,
)


def _series(*values: str) -> pl.Series:
    return pl.Series("v", list(values), dtype=pl.Utf8)


def test_email_pattern_hits_high_on_email_column() -> None:
    s = _series(
        "alice@example.com", "bob@example.org", "carol@test.co",
        "dave@example.com", "eve@example.io",
    )
    hits = pattern_hits(s)
    assert hits["email"] >= 0.95


def test_pattern_hits_filters_sub_5pct() -> None:
    """One 'random' email amongst 100 strings shouldn't show up."""
    values = ["random"] * 100 + ["alice@example.com"]
    hits = pattern_hits(_series(*values))
    # 1/101 ≈ 0.0099, below the 0.05 floor → email absent.
    assert "email" not in hits


def test_pattern_hits_returns_empty_on_empty_series() -> None:
    s = pl.Series("v", [], dtype=pl.Utf8)
    assert pattern_hits(s) == {}


def test_uuid_pattern() -> None:
    s = _series(
        "550e8400-e29b-41d4-a716-446655440000",
        "550e8400-e29b-41d4-a716-446655440001",
        "550e8400-e29b-41d4-a716-446655440002",
    )
    hits = pattern_hits(s)
    assert hits["uuid"] == 1.0


def test_iso_date_pattern() -> None:
    s = _series("2024-01-15", "2024-02-20", "2024-03-30")
    hits = pattern_hits(s)
    assert hits["iso_date"] == 1.0


def test_german_decimal_pattern() -> None:
    s = _series("1,29", "0,89", "1.234,56", "2.499,99")
    hits = pattern_hits(s)
    assert hits["german_decimal"] == 1.0


def test_us_decimal_pattern_requires_thousands_separator() -> None:
    s = _series("1,234.56", "2,499.99", "12,345.00")
    hits = pattern_hits(s)
    assert hits["us_decimal"] == 1.0


def test_currency_amount() -> None:
    s = _series("$12.50", "$1,200.00", "$0.99")
    hits = pattern_hits(s)
    assert hits["currency_amount"] == 1.0


# --- date_format_candidates ----------------------------------------------


def test_date_format_candidates_iso_winner() -> None:
    s = _series("2024-01-15", "2024-02-20", "2024-03-30", "2024-04-05")
    cands = date_format_candidates(s)
    assert "%Y-%m-%d" in cands
    assert cands["%Y-%m-%d"] == 1.0


def test_date_format_candidates_iso_plus_slash_mix() -> None:
    """ISO + slashed dates mixed; ISO should rank first by hit rate."""
    s = _series(
        "2024-01-15", "2024-02-20", "2024-03-30",
        "01/15/2024",
    )
    cands = date_format_candidates(s)
    iso = cands.get("%Y-%m-%d", 0.0)
    slashed = cands.get("%m/%d/%Y", 0.0)
    assert iso > slashed
    formats = list(cands.keys())
    assert formats[0] == "%Y-%m-%d"


def test_date_format_candidates_filters_below_10pct() -> None:
    values = ["nope"] * 100 + ["2024-01-15"]
    cands = date_format_candidates(_series(*values))
    # 1/101 ≈ 0.0099 → both below 0.1 floor.
    assert cands == {}


# --- timezone_hints -------------------------------------------------------


def test_timezone_hints_all_naive() -> None:
    s = _series(
        "2024-01-15T10:30:00", "2024-02-20T11:00:00", "2024-03-30T12:15:00",
        "2024-04-05T08:45:00",
    )
    hints = timezone_hints(s)
    assert hints is not None
    assert hints["naive_ratio"] == 1.0
    assert hints["offsets"] == []


def test_timezone_hints_mixed_offsets() -> None:
    s = _series(
        "2024-01-15T10:30:00+00:00",
        "2024-02-20T11:00:00+05:30",
        "2024-03-30T12:15:00Z",
        "2024-04-05T08:45:00",  # naive
    )
    hints = timezone_hints(s)
    assert hints is not None
    assert 0.0 < hints["naive_ratio"] < 1.0
    assert "+00:00" in hints["offsets"]
    assert "+05:30" in hints["offsets"]
    assert "Z" in hints["offsets"]


def test_timezone_hints_none_when_not_datetimes() -> None:
    s = _series("hello", "world", "foo", "bar")
    assert timezone_hints(s) is None


def test_pattern_pii_regexes_smoke() -> None:
    """Direct regex fullmatch checks so pii.py can rely on them."""
    assert PATTERNS["email"].fullmatch("a@b.co") is not None
    assert PATTERNS["phone_e164"].fullmatch("+14155551234") is not None
    assert PATTERNS["ip_v4"].fullmatch("192.168.1.1") is not None
    assert PATTERNS["national_id_us_ssn"].fullmatch("123-45-6789") is not None
    assert PATTERNS["cc_luhn_format"].fullmatch("4242 4242 4242 4242") is not None
