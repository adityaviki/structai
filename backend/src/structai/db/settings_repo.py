"""Settings DB layer.

Stores runtime overrides keyed by string in ``app_settings``. Env vars
always win over DB values; the read functions reflect that.
"""

from __future__ import annotations

import os

from .pools import get_pools

_VALID_KEYS = {
    "anthropic_api_key",
    "default_model",
    "snapshot_keep_last_n",
    "snapshot_max_age_days",
}


async def get_value(key: str) -> str | None:
    if key not in _VALID_KEYS:
        return None
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM app_settings WHERE key = $1", key)
    return val if isinstance(val, str) else None


async def set_value(key: str, value: str) -> None:
    if key not in _VALID_KEYS:
        raise ValueError(f"Unknown setting key: {key!r}")
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            key,
            value,
        )


async def delete_value(key: str) -> None:
    if key not in _VALID_KEYS:
        return
    meta = await get_pools().meta()
    async with meta.acquire() as conn:
        await conn.execute("DELETE FROM app_settings WHERE key = $1", key)


# ---------------------------------------------------------------------------
# Effective accessors: env > DB > built-in defaults.
# ---------------------------------------------------------------------------


async def effective_anthropic_key() -> tuple[str | None, str]:
    """Return ``(key, source)``. source is ``env`` | ``config`` | ``unset``."""

    env = os.environ.get("STRUCTAI_ANTHROPIC_API_KEY")
    if env:
        return env, "env"
    db = await get_value("anthropic_api_key")
    if db:
        return db, "config"
    return None, "unset"


async def effective_default_model() -> tuple[str, str]:
    env = os.environ.get("STRUCTAI_DEFAULT_MODEL")
    if env:
        return env, "env"
    db = await get_value("default_model")
    if db:
        return db, "config"
    return "claude-sonnet-4-6", "default"


async def effective_retention() -> tuple[int, int]:
    """Return ``(keep_last_n, max_age_days)``."""

    n_str = await get_value("snapshot_keep_last_n")
    age_str = await get_value("snapshot_max_age_days")
    n = int(n_str) if n_str and n_str.isdigit() else 10
    age = int(age_str) if age_str and age_str.isdigit() else 30
    return n, age
