"""PK-score heuristic tests (CHECKLIST.md line 137)."""

from __future__ import annotations

from structai_core.profile.heuristics import pk_score
from structai_core.profile.models import InferredType


def test_pk_score_perfect_id_column() -> None:
    """100 unique non-null int values named `id` → high PK score."""
    score = pk_score(
        distinct_count=100,
        null_count=0,
        total_rows=100,
        inferred_type=InferredType.int,
        raw_name="id",
        leading_zero_ratio=0.0,
    )
    assert score >= 0.95


def test_pk_score_non_pk_column() -> None:
    """Low-cardinality non-null string column scores below 0.7."""
    score = pk_score(
        distinct_count=3,
        null_count=0,
        total_rows=100,
        inferred_type=InferredType.string,
        raw_name="category",
        leading_zero_ratio=0.0,
    )
    assert score < 0.7


def test_pk_score_all_null_is_zero() -> None:
    """All-null column → 0.0, not NaN."""
    score = pk_score(
        distinct_count=0,
        null_count=100,
        total_rows=100,
        inferred_type=InferredType.string,
        raw_name="empty",
        leading_zero_ratio=0.0,
    )
    assert score == 0.0


def test_pk_score_zero_rows_is_zero() -> None:
    score = pk_score(
        distinct_count=0,
        null_count=0,
        total_rows=0,
        inferred_type=InferredType.int,
        raw_name="id",
        leading_zero_ratio=0.0,
    )
    assert score == 0.0


def test_pk_score_partial_nulls_drops_score() -> None:
    base = pk_score(
        distinct_count=100, null_count=0, total_rows=100,
        inferred_type=InferredType.int, raw_name="id", leading_zero_ratio=0.0,
    )
    partial = pk_score(
        distinct_count=80, null_count=20, total_rows=100,
        inferred_type=InferredType.int, raw_name="id", leading_zero_ratio=0.0,
    )
    assert partial < base


def test_pk_score_leading_zero_high_drops_stable_id() -> None:
    """Columns dominated by leading zeros lose half the stable-id weight."""
    high_lz = pk_score(
        distinct_count=100, null_count=0, total_rows=100,
        inferred_type=InferredType.string, raw_name="zip",
        leading_zero_ratio=0.95,
    )
    no_lz = pk_score(
        distinct_count=100, null_count=0, total_rows=100,
        inferred_type=InferredType.string, raw_name="zip",
        leading_zero_ratio=0.0,
    )
    assert high_lz < no_lz


def test_pk_score_name_hint_helps() -> None:
    """Same shape; only the column name differs."""
    with_hint = pk_score(
        distinct_count=100, null_count=0, total_rows=100,
        inferred_type=InferredType.int, raw_name="customer_id",
        leading_zero_ratio=0.0,
    )
    without_hint = pk_score(
        distinct_count=100, null_count=0, total_rows=100,
        inferred_type=InferredType.int, raw_name="customer",
        leading_zero_ratio=0.0,
    )
    assert with_hint > without_hint


def test_pk_score_single_row_does_not_crash() -> None:
    """Single-row file is degenerate but must not produce NaN."""
    score = pk_score(
        distinct_count=1, null_count=0, total_rows=1,
        inferred_type=InferredType.int, raw_name="id",
        leading_zero_ratio=0.0,
    )
    assert 0.0 <= score <= 1.0
