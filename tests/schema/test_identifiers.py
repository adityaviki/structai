"""Identifier sanitization tests (CHECKLIST.md line 139)."""

from __future__ import annotations

import pytest

from structai_core.schema.identifiers import (
    MAX_IDENTIFIER_LEN,
    POSTGRES_RESERVED,
    sanitize,
    sanitize_columns,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Hello World", "hello_world"),
        ("  spaced  ", "spaced"),
        ("UPPERCASE", "uppercase"),
        ("MixedCase_123", "mixedcase_123"),
        ("a__b___c", "a_b_c"),
        ("---weird!chars***", "weird_chars"),
        ("foo bar / baz", "foo_bar_baz"),
    ],
)
def test_sanitize_basic_normalization(raw: str, expected: str) -> None:
    assert sanitize(raw) == expected


def test_sanitize_leading_digit_gets_underscore_prefix() -> None:
    assert sanitize("123abc") == "_123abc"
    assert sanitize("9") == "_9"


def test_sanitize_empty_or_whitespace_returns_underscore_col() -> None:
    assert sanitize("") == "_col"
    assert sanitize("   ") == "_col"
    assert sanitize("___") == "_col"
    assert sanitize("***") == "_col"


def test_sanitize_postgres_reserved_words_get_col_suffix() -> None:
    assert sanitize("select") == "select_col"
    assert sanitize("Order") == "order_col"
    assert sanitize("group") == "group_col"
    assert sanitize("user") == "user_col"
    assert sanitize("table") == "table_col"


def test_sanitize_non_reserved_passes_through() -> None:
    # 'name' is not in the catcode='R' set in PG 16.
    assert sanitize("name") == "name"
    assert "name" not in POSTGRES_RESERVED


def test_sanitize_nfkc_handles_compatibility_decomposition() -> None:
    # Full-width forms decompose to ASCII via NFKC.
    assert sanitize("ＡＢＣ") == "abc"
    # Ligatures decompose too.
    assert sanitize("ﬁle") == "file"


def test_sanitize_non_ascii_letters_replaced_with_underscore() -> None:
    # 'é' is a single composed codepoint under NFKC; the regex replaces it.
    # Expected: "café" → "caf" (trailing underscore stripped).
    assert sanitize("café") == "caf"
    # All-non-ASCII falls back.
    assert sanitize("中文") == "_col"


def test_sanitize_truncates_to_63_chars() -> None:
    raw = "a" * 100
    result = sanitize(raw)
    assert len(result) == MAX_IDENTIFIER_LEN
    assert result == "a" * MAX_IDENTIFIER_LEN


def test_sanitize_columns_simple_mapping() -> None:
    out = sanitize_columns(["First Name", "Last Name", "Email"])
    assert out == {
        "First Name": "first_name",
        "Last Name": "last_name",
        "Email": "email",
    }


def test_sanitize_columns_resolves_collisions_with_n_suffix() -> None:
    # Different raw names that sanitize to the same safe name get _2, _3, ...
    out = sanitize_columns(["Foo", "FOO", "foo "])
    safes = list(out.values())
    assert sorted(safes) == ["foo", "foo_2", "foo_3"]
    # All three raw keys are present.
    assert set(out.keys()) == {"Foo", "FOO", "foo "}


def test_sanitize_columns_collision_truncates_base_to_fit_suffix() -> None:
    long_base = "x" * 65  # would be truncated to 63 by sanitize()
    out = sanitize_columns([long_base, long_base + " "])
    safes = list(out.values())
    # First name takes the truncated 63-char base.
    assert any(s == "x" * 63 for s in safes)
    # Second one fits the _2 suffix within 63 chars total.
    assert any(s.endswith("_2") and len(s) == 63 for s in safes)


def test_sanitize_columns_reserved_word_then_collision() -> None:
    """A reserved word should get the _col suffix first; if a literal
    `select_col` also appears, the second collides and becomes
    `select_col_2`."""
    out = sanitize_columns(["select", "select_col"])
    assert out["select"] == "select_col"
    assert out["select_col"] == "select_col_2"


def test_sanitize_columns_preserves_input_order() -> None:
    raw = ["zeta", "alpha", "beta"]
    out = sanitize_columns(raw)
    assert list(out.keys()) == raw


def test_sanitize_empty_column_name_uses_col_fallback() -> None:
    out = sanitize_columns(["", "name", ""])
    # Two empty raw names collide on dict key; only the last "" survives.
    # But the safe name "_col" still gets _2 / _3 assigned during iteration.
    assert "_col" in out.values() or "_col_2" in out.values()
