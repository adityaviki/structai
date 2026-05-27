"""Redis pubsub for live import-run events (D10).

Publishers (the orchestrator) call ``publish`` with a small dict; the SSE
handler in ``api/runs.py`` subscribes to the same channel and forwards
events to the browser.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from ..settings import get_settings


def channel(run_id: str) -> str:
    return f"run:{run_id}"


_publisher: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _publisher
    if _publisher is None:
        _publisher = aioredis.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _publisher


async def publish(run_id: str, event: dict[str, Any]) -> None:
    payload = json.dumps(event)
    await _client().publish(channel(run_id), payload)


async def close() -> None:
    global _publisher
    if _publisher is not None:
        await _publisher.aclose()
        _publisher = None
