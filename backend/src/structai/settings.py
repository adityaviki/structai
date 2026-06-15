from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_workspace() -> Path:
    return Path.home() / ".local" / "share" / "structai"


class Settings(BaseSettings):
    """Process-wide configuration. Read from env vars (STRUCTAI_*) or .env."""

    model_config = SettingsConfigDict(
        env_prefix="STRUCTAI_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres URL with CREATEDB privilege. Used both to connect to the
    # cluster (for CREATE/DROP DATABASE) and as the base for per-project
    # connection strings.
    pg_url: str = "postgresql://postgres@127.0.0.1:5432/postgres"

    # Postgres database name that holds app metadata (D3).
    meta_db_name: str = "structai_meta"

    # Redis URL for the arq queue and pub/sub channels (D9).
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Anthropic API key for the LLM agent (D5a). Optional in Phase 0 because
    # nothing calls the LLM yet, but warned about on startup.
    anthropic_api_key: str | None = None

    # Default Anthropic model (D5a).
    default_model: str = "claude-sonnet-4-6"

    # Workspace root for documents/, runs/, config (D8).
    workspace: Path = Field(default_factory=_default_workspace)

    # API server bind. Binds to loopback only by default (D1, D7).
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Frontend dev origin, for CORS in case the user runs the FE without the
    # Vite proxy (default flow uses the proxy and doesn't need CORS).
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173",)

    # --- Authentication (single shared login; no account creation) ---
    # The app is single-tenant: there is one login, configured here. Set
    # ``auth_password`` to turn protection on. While it is empty the API and
    # UI stay open (handy for local dev and the test suite).
    auth_username: str = "admin"
    auth_password: str | None = None
    # Optional explicit signing key for session cookies. If unset, the key is
    # derived from the password, so sessions survive restarts and are
    # invalidated automatically when the password changes.
    auth_secret: str | None = None
    # Session lifetime in hours (default: two weeks).
    auth_session_ttl_hours: int = 24 * 14

    @property
    def auth_enabled(self) -> bool:
        """Auth is enforced only once a non-empty password is configured."""

        return bool(self.auth_password)


def get_settings() -> Settings:
    return Settings()
