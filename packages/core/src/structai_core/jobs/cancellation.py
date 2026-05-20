"""Cooperative cancellation token.

The worker passes a `CancellationToken` to every task. The heartbeat loop
flips it to `cancelled` if `jobs.cancel_requested` becomes true (or if the
job loses its lease). Tasks call `raise_if_cancelled()` at step boundaries
— plan §8.4 requires this between staging steps so cancellation rolls back
staging and marks the import_run `cancelled`.
"""

from __future__ import annotations


class JobCancelled(Exception):
    """Raised by `CancellationToken.raise_if_cancelled` when cancellation is requested."""


class CancellationToken:
    __slots__ = ("_cancelled",)

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise JobCancelled()
