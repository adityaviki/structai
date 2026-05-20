"""`structai_core.config.Settings` behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from structai_core.config import Settings

# Env vars that the test conftest sets globally; tests that exercise default
# behaviour or .env loading must wipe these via monkeypatch first.
ALL_SETTINGS_ENV_VARS = (
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
    "STRUCTAI_USER_SCHEMA",
    "STRUCTAI_DATA_DIR",
    "STRUCTAI_MAX_UPLOAD_BYTES",
    "STRUCTAI_RETENTION_DAYS",
    "ANTHROPIC_API_KEY",
    "STRUCTAI_ALLOW_RAW_LLM_SAMPLES",
    "STRUCTAI_WORKER_HEARTBEAT_SECS",
    "STRUCTAI_WORKER_LEASE_SECS",
    "STRUCTAI_WORKER_POLL_INTERVAL_SECS",
)


def _wipe(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ALL_SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _wipe(monkeypatch)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://u:p@h:1/db\n"
        "DATABASE_URL_SYNC=postgresql+psycopg://u:p@h:1/db\n"
        "ANTHROPIC_API_KEY=sk-test\n"
    )
    monkeypatch.chdir(tmp_path)

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:1/db"
    assert s.database_url_sync == "postgresql+psycopg://u:p@h:1/db"
    assert s.anthropic_api_key == "sk-test"


def test_env_var_overrides_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wipe(monkeypatch)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=from-env-file\nDATABASE_URL_SYNC=from-env-file\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "from-env-var")
    monkeypatch.setenv("DATABASE_URL_SYNC", "from-env-var")

    s = Settings()
    assert s.database_url == "from-env-var"
    assert s.database_url_sync == "from-env-var"


def test_defaults_for_optional_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wipe(monkeypatch)
    monkeypatch.chdir(tmp_path)  # no .env in CWD
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("DATABASE_URL_SYNC", "x")

    s = Settings()
    assert s.user_schema == "structai_user"
    assert s.data_dir == Path("./data")
    assert s.max_upload_bytes == 209_715_200
    assert s.retention_days == 30
    assert s.anthropic_api_key == ""
    assert s.allow_raw_llm_samples is False
    assert s.worker_heartbeat_secs == 10
    assert s.worker_lease_secs == 60
    assert s.worker_poll_interval_secs == 1


def test_missing_required_field_errors_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wipe(monkeypatch)
    monkeypatch.chdir(tmp_path)  # no .env

    with pytest.raises(ValidationError) as exc_info:
        Settings()
    err_text = str(exc_info.value)
    assert "DATABASE_URL" in err_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("True", True), ("1", True), ("false", False), ("0", False)],
)
def test_allow_raw_llm_samples_parses_bool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    _wipe(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("DATABASE_URL_SYNC", "x")
    monkeypatch.setenv("STRUCTAI_ALLOW_RAW_LLM_SAMPLES", raw)

    assert Settings().allow_raw_llm_samples is expected


def test_user_schema_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _wipe(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("DATABASE_URL_SYNC", "x")
    monkeypatch.setenv("STRUCTAI_USER_SCHEMA", "custom_managed")

    assert Settings().user_schema == "custom_managed"


def test_worker_tunables_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wipe(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("DATABASE_URL_SYNC", "x")
    monkeypatch.setenv("STRUCTAI_WORKER_HEARTBEAT_SECS", "3")
    monkeypatch.setenv("STRUCTAI_WORKER_LEASE_SECS", "120")
    monkeypatch.setenv("STRUCTAI_WORKER_POLL_INTERVAL_SECS", "5")

    s = Settings()
    assert s.worker_heartbeat_secs == 3
    assert s.worker_lease_secs == 120
    assert s.worker_poll_interval_secs == 5
