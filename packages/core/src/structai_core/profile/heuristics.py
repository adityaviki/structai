"""PK-score heuristic.

Plan §5 line 169; CHECKLIST.md line 91. A simple weighted sum of
uniqueness + non-null + stable-id-look + name-hint. Never authoritative
— the agent (Phase 2) uses it as one signal among many to nominate a
primary key. All-null columns score 0.0 (not NaN) so downstream code
can sort safely.
"""

from __future__ import annotations

import re

from structai_core.profile.models import InferredType

_NAME_HINT = re.compile(r"(^|_)(id|key|uuid|code)($|_)", re.IGNORECASE)

# Weights sum to 1.0.
_W_UNIQUENESS = 0.5
_W_NON_NULL = 0.3
_W_STABLE_ID = 0.15
_W_NAME_HINT = 0.05


def pk_score(
    *,
    distinct_count: int,
    null_count: int,
    total_rows: int,
    inferred_type: InferredType,
    raw_name: str,
    leading_zero_ratio: float,
) -> float:
    """Returns a value in [0, 1]. Higher = more PK-like.

    All-null / empty / degenerate inputs return 0.0, never NaN.
    """
    if total_rows <= 0:
        return 0.0

    non_null_rows = max(total_rows - null_count, 0)
    uniqueness = (distinct_count / non_null_rows) if non_null_rows > 0 else 0.0
    uniqueness = min(uniqueness, 1.0)

    non_null = 1.0 - (null_count / total_rows)

    stable_id = (
        1.0
        if inferred_type in {InferredType.int, InferredType.string}
        and leading_zero_ratio < 0.5
        else 0.5
    )

    name_hint = 1.0 if _NAME_HINT.search(raw_name) else 0.0

    # An all-null column has non_null_rows=0 → uniqueness=0 → score should be 0.
    if non_null_rows == 0:
        return 0.0

    score = (
        _W_UNIQUENESS * uniqueness
        + _W_NON_NULL * non_null
        + _W_STABLE_ID * stable_id
        + _W_NAME_HINT * name_hint
    )
    return round(score, 3)
