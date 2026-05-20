"""`CancellationToken` semantics."""

from __future__ import annotations

import pytest

from structai_core.jobs.cancellation import CancellationToken, JobCancelled


def test_token_starts_not_cancelled() -> None:
    t = CancellationToken()
    assert t.is_cancelled is False
    t.raise_if_cancelled()  # no-op


def test_cancel_flips_state() -> None:
    t = CancellationToken()
    t.cancel()
    assert t.is_cancelled is True


def test_raise_if_cancelled_raises_after_cancel() -> None:
    t = CancellationToken()
    t.cancel()
    with pytest.raises(JobCancelled):
        t.raise_if_cancelled()


def test_cancel_is_idempotent() -> None:
    t = CancellationToken()
    t.cancel()
    t.cancel()
    assert t.is_cancelled is True
    with pytest.raises(JobCancelled):
        t.raise_if_cancelled()


def test_raise_if_cancelled_remains_raising() -> None:
    """Once cancelled, every call raises — cancellation isn't a one-shot signal."""
    t = CancellationToken()
    t.cancel()
    with pytest.raises(JobCancelled):
        t.raise_if_cancelled()
    with pytest.raises(JobCancelled):
        t.raise_if_cancelled()
