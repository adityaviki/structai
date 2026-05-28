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
    prefix; the 16 char suffixes after must still differ since we keep
    16+ random chars."""

    a = _snapshot_name("structai_proj_12345678", "01KSPPMRBP" + "ABCDEFGHIJKLMNOP")
    b = _snapshot_name("structai_proj_12345678", "01KSPPMRBP" + "ZZZZZZZZZZZZZZZZ")
    assert a != b


def test_very_long_project_is_truncated_but_suffix_preserved() -> None:
    long_proj = "structai_" + "x" * 80  # 89 chars
    name = _snapshot_name(long_proj, "01KSPPMRBPABCDEFGHIJKLMNOP")
    assert len(name) == 63
    # 63 - 6 ("_snap_") - 41 (project truncation) = 16 suffix chars
    assert name.endswith("_snap_01ksppmrbpabcdef")  # 16 chars of run_id
