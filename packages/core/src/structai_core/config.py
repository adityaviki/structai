"""Application settings.

All env vars carry the `STRUCTAI_` prefix except database URLs (which use
the standard `DATABASE_URL` / `DATABASE_URL_SYNC` names so external tools
like Alembic and `psql` can read them too).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database -------------------------------------------------------------
    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str = Field(alias="DATABASE_URL_SYNC")
    user_schema: str = Field(default="structai_user", alias="STRUCTAI_USER_SCHEMA")

    # --- Storage --------------------------------------------------------------
    data_dir: Path = Field(default=Path("./data"), alias="STRUCTAI_DATA_DIR")
    max_upload_bytes: int = Field(default=209_715_200, alias="STRUCTAI_MAX_UPLOAD_BYTES")
    retention_days: int = Field(default=30, alias="STRUCTAI_RETENTION_DAYS")

    # --- LLM ------------------------------------------------------------------
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    allow_raw_llm_samples: bool = Field(
        default=False,
        alias="STRUCTAI_ALLOW_RAW_LLM_SAMPLES",
    )

    # --- Worker ---------------------------------------------------------------
    worker_heartbeat_secs: int = Field(default=10, alias="STRUCTAI_WORKER_HEARTBEAT_SECS")
    worker_lease_secs: int = Field(default=60, alias="STRUCTAI_WORKER_LEASE_SECS")
    worker_poll_interval_secs: int = Field(default=1, alias="STRUCTAI_WORKER_POLL_INTERVAL_SECS")
