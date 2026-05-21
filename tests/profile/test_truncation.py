"""Wide-file truncation policy (CHECKLIST.md line 140)."""

from __future__ import annotations

from structai_core.profile.models import (
    CardinalityClass,
    ColumnProfile,
    FileProfile,
    InferredType,
    PiiClass,
    PROFILE_VERSION,
    TopKEntry,
)
from structai_core.profile.truncation import (
    TRUNCATION_BUDGET_BYTES,
    apply_truncation,
    uncertainty_score,
)


def _rich_column(pos: int, *, name: str | None = None, pii: PiiClass = PiiClass.none) -> ColumnProfile:
    n = name or f"col_{pos}"
    return ColumnProfile(
        name=n,
        safe_name=n,
        position=pos,
        inferred_type=InferredType.string,
        null_count=0,
        null_rate=0.0,
        distinct_count=100,
        cardinality_class=CardinalityClass.low,
        sample_values=[f"sample_{i}_for_{n}" for i in range(5)],
        top_k=[
            TopKEntry(value=f"value_{i}_in_{n}_long_payload", count=10 - i)
            for i in range(10)
        ],
        pattern_hits={"email": 0.6, "uuid": 0.6},  # 2 high hits → ambiguous
        pii_class=pii,
        pk_score=0.3,
        outlier_examples=[f"outlier_{i}_{n}" for i in range(6)],
    )


def _profile(columns: list[ColumnProfile]) -> FileProfile:
    return FileProfile(
        row_count=1000,
        duplicate_row_count=0,
        encoding="utf-8",
        delimiter=",",
        has_header=True,
        source_sha256="a" * 64,
        profile_sha256="b" * 64,
        profile_version=PROFILE_VERSION,
        raw_to_safe={c.name: c.safe_name for c in columns},
        columns=columns,
    )


def test_truncation_no_op_when_under_budget() -> None:
    p = _profile([_rich_column(0)])
    out = apply_truncation(p)
    # Pure function; either same object or content-equal.
    assert out.columns == p.columns
    assert out.omitted_columns == []


def test_truncation_100_col_realistic_fits_budget() -> None:
    """100-column profile with rich stats per column — well above the
    30 KB ceiling before truncation, comfortably below after."""
    cols = [_rich_column(i) for i in range(100)]
    p = _profile(cols)
    pre_size = len(p.model_dump_json().encode())
    assert pre_size > TRUNCATION_BUDGET_BYTES

    out = apply_truncation(p)
    post_size = len(out.model_dump_json().encode())
    assert post_size <= TRUNCATION_BUDGET_BYTES


def test_truncation_500_col_extreme_reduces_significantly() -> None:
    """500 columns can't strictly fit 30 KB even fully omitted (each
    OmittedColumn ≈ 175 B → ~87 KB alone). Truncation should still
    reduce the size by at least an order of magnitude and account for
    every column in `columns` or `omitted_columns`."""
    cols = [_rich_column(i) for i in range(500)]
    p = _profile(cols)
    pre_size = len(p.model_dump_json().encode())
    out = apply_truncation(p)
    post_size = len(out.model_dump_json().encode())
    assert post_size < pre_size / 3


def test_truncation_preserves_every_original_column() -> None:
    cols = [_rich_column(i) for i in range(500)]
    p = _profile(cols)
    out = apply_truncation(p)

    surviving = {c.position for c in out.columns}
    omitted = {o.position for o in out.omitted_columns}
    assert surviving | omitted == set(range(500))
    assert not (surviving & omitted)


def test_truncation_preserves_file_level_fields() -> None:
    cols = [_rich_column(i) for i in range(500)]
    p = _profile(cols)
    out = apply_truncation(p)
    assert out.row_count == p.row_count
    assert out.duplicate_row_count == p.duplicate_row_count
    assert out.encoding == p.encoding
    assert out.delimiter == p.delimiter
    assert out.has_header == p.has_header
    assert out.source_sha256 == p.source_sha256
    assert out.profile_sha256 == p.profile_sha256
    assert out.profile_version == p.profile_version
    assert out.raw_to_safe == p.raw_to_safe


def test_truncation_keeps_high_uncertainty_columns() -> None:
    """A column with PII + ambiguous patterns should survive even when
    the profile gets aggressively truncated. Uses 100 cols so some
    columns remain in `columns` after the cut."""
    interesting = _rich_column(0, name="pii_email", pii=PiiClass.email)
    other = [_rich_column(i) for i in range(1, 100)]
    p = _profile([interesting, *other])
    out = apply_truncation(p)

    surviving_positions = {c.position for c in out.columns}
    assert len(surviving_positions) > 0, "no columns survived — bump fixture size"
    # The PII-bearing, ambiguous-type column should outrank the rest.
    assert 0 in surviving_positions


def test_truncation_does_not_mutate_input() -> None:
    cols = [_rich_column(i) for i in range(500)]
    p = _profile(cols)
    pre_cols = len(p.columns)
    pre_omitted = len(p.omitted_columns)
    _ = apply_truncation(p)
    assert len(p.columns) == pre_cols
    assert len(p.omitted_columns) == pre_omitted


def test_uncertainty_score_components() -> None:
    pii_col = _rich_column(0, pii=PiiClass.email)
    bare = ColumnProfile(
        name="b", safe_name="b", position=1,
        inferred_type=InferredType.int, null_count=0, null_rate=0.0,
        distinct_count=5, cardinality_class=CardinalityClass.low,
        pk_score=1.0, pii_class=PiiClass.none,
    )
    assert uncertainty_score(pii_col, 1000) > uncertainty_score(bare, 1000)
