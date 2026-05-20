"""Shared FastAPI dependencies.

Settings live in `structai_core.config.Settings`; the async DB session
arrives with the migrations commit.
"""

from __future__ import annotations

from functools import lru_cache

from structai_core.config import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
