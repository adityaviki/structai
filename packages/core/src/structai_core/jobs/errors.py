"""Job error classes.

Workers signal failure mode by raising one of these. Anything that isn't
caught is treated as `RetryableError` by the worker loop — failing closed
on the side of "try again" is safer than failing closed on "give up".
"""

from __future__ import annotations


class JobError(Exception):
    """Base class for worker-raised job errors."""


class RetryableError(JobError):
    """Failure that should be retried (transient I/O, lock contention, etc.)."""


class TerminalError(JobError):
    """Failure that should NOT be retried (bad input, schema mismatch, etc.)."""
