"""Worker task registry.

Each `jobs.kind` value maps to an async callable. Tasks receive a session,
the job payload, and a `CancellationToken` they must check at step
boundaries (plan §8.4). Tasks raise `RetryableError` / `TerminalError` to
control retry behavior; anything else is treated as retryable.

Phase 1+ register concrete tasks (`profile_file`, `run_agent_session`,
`execute_pipeline`); Phase 0 only wires the dispatch table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from structai_core.jobs import CancellationToken, TerminalError

TaskFn = Callable[[AsyncSession, dict[str, Any], CancellationToken], Awaitable[None]]

REGISTRY: dict[str, TaskFn] = {}


def register(kind: str) -> Callable[[TaskFn], TaskFn]:
    """Decorator: add a task to the dispatch registry."""

    def _wrap(fn: TaskFn) -> TaskFn:
        if kind in REGISTRY:
            raise RuntimeError(f"task kind {kind!r} already registered")
        REGISTRY[kind] = fn
        return fn

    return _wrap


async def dispatch(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    token: CancellationToken,
) -> None:
    fn = REGISTRY.get(kind)
    if fn is None:
        raise TerminalError(f"unknown job kind: {kind!r}")
    await fn(session, payload, token)
