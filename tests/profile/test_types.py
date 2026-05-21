"""Type inference + leading-zero / decimal-separator / currency tests
(CHECKLIST.md line 135)."""

from __future__ import annotations

import polars as pl

from structai_core.profile.models import InferredType
from structai_core.profile.types import infer_type


def _series(*values: str) -> pl.Series:
    return pl.Series("v", list(values), dtype=pl.Utf8)


def test_pure_int_column_stays_int() -> None:
    s = _series("1", "2", "3", "4", "5", "100", "200")
    result = infer_type(s, name="id")
    assert result.inferred_type == InferredType.int
    assert result.leading_zero_ratio == 0.0


def test_leading_zero_ids_demoted_to_string() -> None:
    """ZIPs / SKUs that look int-shaped but have leading zeros stay as
    string — type preservation rule, plan §5 line 174."""
    s = _series("00123", "00456", "00789", "01234")
    result = infer_type(s, name="zip")
    assert result.inferred_type == InferredType.string
    assert result.leading_zero_ratio == 1.0


def test_mixed_leading_zero_demotes_above_5pct() -> None:
    # 1 leading-zero in 10 values = 10% > 5% threshold.
    s = _series("00123", "1", "2", "3", "4", "5", "6", "7", "8", "9")
    result = infer_type(s, name="code")
    assert result.inferred_type == InferredType.string


def test_below_threshold_stays_int() -> None:
    """A single leading-zero value in a long pure-int column does NOT
    demote (below the 5% threshold)."""
    values = ["00123"] + [str(i) for i in range(1, 100)]
    s = _series(*values)
    result = infer_type(s, name="id")
    assert result.inferred_type == InferredType.int


def test_german_decimal_float_detection() -> None:
    s = _series("1,29", "0,89", "1.234,56", "2.499,99")
    result = infer_type(s, name="preis")
    assert result.inferred_type == InferredType.float
    assert result.decimal_separator == ","
    assert result.thousands_separator == "."


def test_us_decimal_with_thousands_separator() -> None:
    s = _series("1,234.56", "2,499.99", "12,345.00", "999.99")
    # 3 of 4 hit us_decimal (`999.99` is plain_float). With strict 0.9
    # threshold we may not hit; let's use 4 us_decimal values.
    s = _series("1,234.56", "2,499.99", "12,345.00", "100,000.00")
    result = infer_type(s, name="amount")
    assert result.inferred_type == InferredType.float
    assert result.decimal_separator == "."
    assert result.thousands_separator == ","


def test_plain_float_without_thousands() -> None:
    s = _series("1.5", "2.7", "3.14159", "0.001", "100.5")
    result = infer_type(s, name="value")
    assert result.inferred_type == InferredType.float
    assert result.decimal_separator == "."
    assert result.thousands_separator is None


def test_currency_detection() -> None:
    s = _series("$1,200.00", "$0.99", "$15.50", "$100.00")
    result = infer_type(s, name="price")
    assert result.inferred_type == InferredType.float
    assert result.currency_symbol == "$"


def test_currency_symbol_euro() -> None:
    s = _series("€1,200.00", "€0.99", "€15.50", "€100.00")
    result = infer_type(s, name="price")
    assert result.currency_symbol == "€"


def test_percent_detection() -> None:
    s = _series("12.5%", "87.0%", "1.2%", "99.9%")
    result = infer_type(s, name="rate")
    assert result.inferred_type == InferredType.float
    assert result.percent_unit is True


def test_iso_date_detection() -> None:
    s = _series("2024-01-15", "2024-02-20", "2024-03-30", "2024-04-05")
    result = infer_type(s, name="created_at")
    assert result.inferred_type == InferredType.date


def test_iso_datetime_detection() -> None:
    s = _series(
        "2024-01-15T10:30:00",
        "2024-02-20T11:00:00",
        "2024-03-30T12:15:00",
        "2024-04-05T08:45:00",
    )
    result = infer_type(s, name="ts")
    assert result.inferred_type == InferredType.datetime


def test_bool_detection() -> None:
    s = _series("true", "false", "true", "false", "True", "FALSE")
    result = infer_type(s, name="flag")
    assert result.inferred_type == InferredType.bool


def test_yes_no_bool() -> None:
    s = _series("yes", "no", "yes", "no", "YES", "NO")
    result = infer_type(s, name="optin")
    assert result.inferred_type == InferredType.bool


def test_zero_one_not_treated_as_bool() -> None:
    """0/1 columns are int, not bool (plan §5 — avoid false positives)."""
    s = _series("0", "1", "0", "1", "1", "0")
    result = infer_type(s, name="flag")
    assert result.inferred_type == InferredType.int


def test_mixed_strings_and_ints_stays_string() -> None:
    s = _series("42", "hello", "17", "world", "99")
    result = infer_type(s, name="value")
    assert result.inferred_type == InferredType.string


def test_pure_string_column() -> None:
    s = _series("alice", "bob", "carol", "dave")
    result = infer_type(s, name="name")
    assert result.inferred_type == InferredType.string


def test_json_object_detection() -> None:
    s = _series('{"a": 1}', '{"b": 2}', '{"c": 3}')
    result = infer_type(s, name="payload")
    assert result.inferred_type == InferredType.json


def test_empty_sample_defaults_to_string() -> None:
    s = pl.Series("v", [None, None, None], dtype=pl.Utf8)
    result = infer_type(s, name="empty")
    assert result.inferred_type == InferredType.string


def test_empty_series_defaults_to_string() -> None:
    s = pl.Series("v", [], dtype=pl.Utf8)
    result = infer_type(s, name="empty")
    assert result.inferred_type == InferredType.string
