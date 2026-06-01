"""Snapshot-name uniqueness — D15."""

from __future__ import annotations

from structai.pipeline.orchestrator import _snapshot_name


def test_short_project_keeps_full_run_id() -> None:
    name = _snapshot_name(
        "structai_aethair_01ksppm6",
        "01KSPPMRBPPCXYZABCDEFGHIJKL",
    )
    assert name == "structai_aethair_01ksppm6_snap_01ksppmrbppcxyzabcdefghijkl"
    assert len(name) <= 63


def test_same_millisecond_runs_do_not_collide() -> None:
    """Two ULIDs in the same millisecond share their 10-char timestamp
    prefix; their random tails differ. The snapshot name must keep enough
    of the tail to disambiguate."""

    a = _snapshot_name("structai_proj_12345678", "01KSPPMRBP" + "ABCDEFGHIJKLMNOP")
    b = _snapshot_name("structai_proj_12345678", "01KSPPMRBP" + "ZZZZZZZZZZZZZZZZ")
    assert a != b


def test_monotonic_ulids_with_truncated_project_do_not_collide() -> None:
    """python-ulid's monotonic mode makes same-millisecond ULIDs differ
    only in the LAST few chars (counter increments from the tail). The
    snapshot suffix MUST therefore preserve the tail, not the head — the
    repro that motivated the fix was two run_ids that were identical
    except for the very last character."""

    # 32-char project — same as the live aethair_data project that hit
    # the original bug. Leaves 25 chars of suffix budget.
    project = "structai_aethair_data_2_01kt11rs"
    # Two monotonic ULIDs differing only in the final char.
    a = _snapshot_name(project, "01KT11S3GT9X6KV8FKRH2014MR")
    b = _snapshot_name(project, "01KT11S3GT9X6KV8FKRH2014MS")
    assert a != b


def test_very_long_project_is_truncated_but_random_tail_preserved() -> None:
    long_proj = "structai_" + "x" * 80  # 89 chars
    name = _snapshot_name(long_proj, "01KSPPMRBPABCDEFGHIJKLMNOP")
    assert len(name) == 63
    # 63 - 6 ("_snap_") - 41 (project truncation) = 16 suffix chars.
    # We take the LAST 16 chars of the ULID — the random block where
    # monotonic-mode increments live.
    assert name.endswith("_snap_abcdefghijklmnop")  # last 16 chars, lowercased
