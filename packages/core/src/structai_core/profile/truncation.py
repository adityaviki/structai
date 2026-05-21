"""Wide-file truncation policy.

Plan §5 lines 178-185; CHECKLIST.md line 98. When a profile would
exceed `TRUNCATION_BUDGET_BYTES`, rank columns by uncertainty (high =
more interesting to keep) and iteratively reduce the lowest-ranked
columns to compact `OmittedColumn` entries.

File-level fields are **always** kept. Every original column is
preserved in either `columns` (rich) or `omitted_columns` (compact),
so the agent can drill into omitted ones via `get_column_samples` /
`count_values` later. Reductions happen in batches of 10 to amortize
the JSON-serialize cost.
"""

from __future__ import annotations

from structai_core.profile.models import (
    ColumnProfile,
    FileProfile,
    OmittedColumn,
    PiiClass,
)

TRUNCATION_BUDGET_BYTES = 30 * 1024  # 30 KB
_BATCH_SIZE = 10
_AMBIGUOUS_TYPE_BONUS = 0.3
_PII_BONUS = 0.5
_PATTERN_HIT_FLOOR = 0.5


def uncertainty_score(col: ColumnProfile, row_count: int) -> float:
    """Higher = more interesting (the profile keeps the highest scorers).
    Components: PK-uncertainty + ambiguous-type bonus + distinct ratio +
    PII bonus."""
    rc = max(row_count, 1)
    base = 1.0 - col.pk_score
    high_pattern_hits = sum(
        1 for rate in col.pattern_hits.values() if rate > _PATTERN_HIT_FLOOR
    )
    ambiguous = _AMBIGUOUS_TYPE_BONUS if high_pattern_hits > 1 else 0.0
    distinct_ratio = min(col.distinct_count / rc, 1.0)
    pii_bonus = _PII_BONUS if col.pii_class != PiiClass.none else 0.0
    return base + ambiguous + distinct_ratio + pii_bonus


def apply_truncation(
    profile: FileProfile, *, budget: int = TRUNCATION_BUDGET_BYTES
) -> FileProfile:
    """Pure function. Returns a maybe-shrunk copy of `profile` that fits
    `budget` bytes (best-effort: file-level + every column index slot is
    inviolable)."""

    if _serialized_size(profile) <= budget:
        return profile

    p = profile.model_copy(deep=True)
    queue = sorted(
        p.columns,
        key=lambda c: uncertainty_score(c, p.row_count),
    )

    while queue and _serialized_size(p) > budget:
        batch = queue[:_BATCH_SIZE]
        queue = queue[_BATCH_SIZE:]
        omitted_positions = {c.position for c in batch}
        p.columns = [c for c in p.columns if c.position not in omitted_positions]
        for c in batch:
            p.omitted_columns.append(_to_omitted(c))

    return p


def _to_omitted(col: ColumnProfile) -> OmittedColumn:
    return OmittedColumn(
        name=col.name,
        safe_name=col.safe_name,
        position=col.position,
        inferred_type=col.inferred_type,
        null_rate=col.null_rate,
        distinct_count=col.distinct_count,
        pk_score=col.pk_score,
        reason="wide-file truncation",
    )


def _serialized_size(profile: FileProfile) -> int:
    return len(profile.model_dump_json().encode("utf-8"))
