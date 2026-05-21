"""Per-column compute.

Plan §5 lines 152-170; CHECKLIST.md lines 80-83 + 92. The runner loops
columns in Python and calls `profile_column(series, ...)` per column.
Eager per column: `series` is already materialized (the runner does
`.select(col).collect()` once per column) so all aggregations
(`null_count`, `n_unique`, `value_counts`, length / numeric quantiles,
outlier extraction) run in a single resident-memory pass and the
column is freed before the next one loads.

Returns a **raw** `ColumnProfile`. Redaction (the redacted/raw split)
is the runner's job, applied via `pii.redact_column` over a deep copy.
"""

from __future__ import annotations

import math
from typing import Any

import polars as pl

from structai_core.jobs import CancellationToken
from structai_core.profile import patterns, pii, types
from structai_core.profile.heuristics import pk_score
from structai_core.profile.models import (
    CardinalityClass,
    ColumnProfile,
    InferredType,
    LengthStats,
    Quantiles,
    TopKEntry,
)

_LOW_CARDINALITY_ABS = 50
_LOW_CARDINALITY_RATIO = 0.01
_TOP_K = 10
_SAMPLE_N = 5


def profile_column(
    series: pl.Series,
    *,
    raw_name: str,
    safe_name: str,
    position: int,
    total_rows: int,
    token: CancellationToken,
) -> ColumnProfile:
    """Produce a raw ColumnProfile for a single column."""

    token.raise_if_cancelled()

    null_count = int(series.null_count())
    null_rate = null_count / total_rows if total_rows > 0 else 0.0
    empty_string_count = int((series.fill_null("__null__sentinel__") == "").sum())

    non_null = series.drop_nulls()
    distinct_count = int(non_null.n_unique())
    card_class = _cardinality_class(distinct_count, total_rows, null_count)

    type_info = types.infer_type(series, name=raw_name)
    hits = patterns.pattern_hits(series)
    date_cands = patterns.date_format_candidates(series)
    tz = patterns.timezone_hints(series)
    samples = _sample_values(non_null, _SAMPLE_N)
    top_k = _top_k(non_null, card_class)
    length_stats = _length_stats(non_null) if type_info.inferred_type == InferredType.string else None
    pii_class, pii_warnings = pii.classify(
        pattern_hits=hits,
        values_sample=[str(v) for v in samples if v is not None],
        name=raw_name,
    )

    minimum, maximum, quantiles = _min_max_quantiles(non_null, type_info.inferred_type)
    outlier_examples = _outliers(non_null, type_info.inferred_type)
    score = pk_score(
        distinct_count=distinct_count,
        null_count=null_count,
        total_rows=total_rows,
        inferred_type=type_info.inferred_type,
        raw_name=raw_name,
        leading_zero_ratio=type_info.leading_zero_ratio,
    )

    return ColumnProfile(
        name=raw_name,
        safe_name=safe_name,
        position=position,
        inferred_type=type_info.inferred_type,
        null_count=null_count,
        null_rate=round(null_rate, 4),
        empty_string_count=empty_string_count,
        distinct_count=distinct_count,
        cardinality_class=card_class,
        min=minimum,
        max=maximum,
        quantiles=quantiles,
        sample_values=samples,
        top_k=top_k,
        length_stats=length_stats,
        pattern_hits=hits,
        pii_class=pii_class,
        pii_warnings=pii_warnings,
        date_format_candidates=date_cands or None,
        leading_zero_ratio=(
            type_info.leading_zero_ratio if type_info.leading_zero_ratio > 0 else None
        ),
        decimal_separator=type_info.decimal_separator,
        thousands_separator=type_info.thousands_separator,
        currency_symbol=type_info.currency_symbol,
        percent_unit=type_info.percent_unit,
        unit_hint=type_info.unit_hint,
        timezone_hints=tz,
        outlier_examples=outlier_examples,
        pk_score=score,
    )


# --- Helpers --------------------------------------------------------------


def _cardinality_class(
    distinct_count: int, total_rows: int, null_count: int
) -> CardinalityClass:
    non_null_rows = max(total_rows - null_count, 0)
    if non_null_rows > 0 and distinct_count == non_null_rows:
        return CardinalityClass.unique
    low_threshold = max(_LOW_CARDINALITY_ABS, int(_LOW_CARDINALITY_RATIO * total_rows))
    if distinct_count <= low_threshold:
        return CardinalityClass.low
    return CardinalityClass.high


def _sample_values(non_null: pl.Series, n: int) -> list[Any]:
    if non_null.len() == 0:
        return []
    take = min(n, non_null.len())
    return non_null.sample(take, seed=0).to_list()


def _top_k(non_null: pl.Series, card_class: CardinalityClass) -> list[TopKEntry] | None:
    if card_class == CardinalityClass.high or non_null.len() == 0:
        return None
    vc = non_null.value_counts(sort=True).head(_TOP_K)
    col_name = vc.columns[0]
    return [
        TopKEntry(value=row[col_name], count=int(row["count"]))
        for row in vc.to_dicts()
    ]


def _length_stats(non_null: pl.Series) -> LengthStats | None:
    if non_null.len() == 0:
        return None
    lengths = non_null.cast(pl.Utf8, strict=False).str.len_chars()
    return LengthStats(
        min=int(lengths.min() or 0),
        max=int(lengths.max() or 0),
        p50=int(lengths.quantile(0.5) or 0),
        p99=int(lengths.quantile(0.99) or 0),
    )


def _try_numeric(non_null: pl.Series, target: pl.DataType) -> pl.Series | None:
    try:
        return non_null.cast(target, strict=False).drop_nulls()
    except pl.exceptions.ComputeError:
        return None


def _min_max_quantiles(
    non_null: pl.Series, inferred: InferredType
) -> tuple[Any | None, Any | None, Quantiles | None]:
    if non_null.len() == 0:
        return None, None, None

    if inferred == InferredType.int:
        numeric = _try_numeric(non_null, pl.Int64)
    elif inferred == InferredType.float:
        numeric = _try_numeric(non_null, pl.Float64)
    else:
        numeric = None

    if numeric is not None and numeric.len() > 0:
        return (
            _coerce(numeric.min()),
            _coerce(numeric.max()),
            Quantiles(
                p1=_coerce(numeric.quantile(0.01)),
                p50=_coerce(numeric.quantile(0.5)),
                p99=_coerce(numeric.quantile(0.99)),
            ),
        )

    # Strings / dates / other: lexicographic min/max only.
    return _coerce(non_null.min()), _coerce(non_null.max()), None


def _outliers(non_null: pl.Series, inferred: InferredType) -> list[Any]:
    if non_null.len() == 0:
        return []
    if inferred in (InferredType.int, InferredType.float):
        target = pl.Int64 if inferred == InferredType.int else pl.Float64
        numeric = _try_numeric(non_null, target)
        if numeric is None or numeric.len() < 2:
            return []
        sorted_vals = numeric.sort()
        low = sorted_vals.head(3).to_list()
        high = sorted_vals.tail(3).to_list()
        return [_coerce(v) for v in low + high]
    if inferred == InferredType.string:
        lengths = non_null.str.len_chars()
        df = pl.DataFrame({"v": non_null, "l": lengths}).sort("l")
        shortest = df["v"].head(3).to_list()
        longest = df["v"].tail(3).to_list()
        return shortest + longest
    return []


def _coerce(value: Any) -> Any:
    """Convert NaN to None for JSON safety; pass through otherwise."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value
