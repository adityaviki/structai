"""End-to-end profile runner tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from structai_core.config import Settings
from structai_core.io.sniff import sniff
from structai_core.jobs import CancellationToken
from structai_core.jobs.cancellation import JobCancelled
from structai_core.profile.models import InferredType, PiiClass, PROFILE_VERSION
from structai_core.profile.runner import profile_file

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "csv"


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def settings_allow_raw(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("STRUCTAI_ALLOW_RAW_LLM_SAMPLES", "true")
    return Settings()


async def _run(path: Path, settings: Settings, *, token: CancellationToken | None = None):
    s = sniff(path)
    return await profile_file(
        path,
        sniff=s,
        source_sha256="a" * 64,
        token=token or CancellationToken(),
        settings=settings,
    )


# --- Happy path -----------------------------------------------------------


async def test_runner_bom_fixture(settings: Settings) -> None:
    result = await _run(FIXTURE_DIR / "bom.csv", settings)
    assert result.redacted.row_count == 3
    assert result.redacted.encoding == "utf-8-sig"
    assert result.redacted.delimiter == ","
    assert result.redacted.has_header is True
    assert result.redacted.profile_version == PROFILE_VERSION
    # No PII in this fixture → raw and redacted match.
    assert result.raw.profile_sha256 == result.redacted.profile_sha256


async def test_runner_raw_to_safe_uses_identifier_sanitizer(settings: Settings) -> None:
    result = await _run(FIXTURE_DIR / "german_decimals.csv", settings)
    # All column names are already lowercase ASCII so safe_name == name.
    for raw, safe in result.redacted.raw_to_safe.items():
        assert safe == raw.lower()


async def test_runner_leading_zero_zips_stay_string(settings: Settings) -> None:
    result = await _run(FIXTURE_DIR / "leading_zero_ids.csv", settings)
    zip_col = next(c for c in result.redacted.columns if c.name == "zip")
    assert zip_col.inferred_type == InferredType.string
    assert zip_col.leading_zero_ratio is not None
    assert zip_col.leading_zero_ratio > 0.5


async def test_runner_german_decimals_detected(settings: Settings) -> None:
    result = await _run(FIXTURE_DIR / "german_decimals.csv", settings)
    preis = next(c for c in result.redacted.columns if c.name == "preis")
    assert preis.inferred_type == InferredType.float
    assert preis.decimal_separator == ","
    assert preis.thousands_separator == "."


# --- PII redaction surface ------------------------------------------------


async def test_runner_pii_email_split_artifacts(settings: Settings) -> None:
    result = await _run(FIXTURE_DIR / "pii" / "emails.csv", settings)
    email_raw = next(c for c in result.raw.columns if c.name == "email")
    email_red = next(c for c in result.redacted.columns if c.name == "email")
    assert email_raw.pii_class == PiiClass.email
    # Raw artifact keeps the actual addresses.
    assert any("@" in str(v) for v in email_raw.sample_values)
    # Redacted artifact replaces with placeholders.
    assert all(str(v).startswith("<EMAIL_") for v in email_red.sample_values)


async def test_runner_allow_raw_round_trips_un_redacted(
    settings_allow_raw: Settings,
) -> None:
    result = await _run(
        FIXTURE_DIR / "pii" / "emails.csv", settings_allow_raw
    )
    email_red = next(c for c in result.redacted.columns if c.name == "email")
    # `allow_raw_llm_samples=true` → no placeholders.
    assert all("@" in str(v) for v in email_red.sample_values)


# --- Cancellation --------------------------------------------------------


async def test_runner_pre_cancelled_raises_mid_loop(settings: Settings) -> None:
    """`token.cancel()` before `profile_file` starts → first column
    iteration trips `raise_if_cancelled` → `JobCancelled` propagates."""
    token = CancellationToken()
    token.cancel()
    with pytest.raises(JobCancelled):
        await _run(FIXTURE_DIR / "leading_zero_ids.csv", settings, token=token)


# --- Determinism / sha ----------------------------------------------------


async def test_runner_profile_sha_stable_across_runs(settings: Settings) -> None:
    a = await _run(FIXTURE_DIR / "bom.csv", settings)
    b = await _run(FIXTURE_DIR / "bom.csv", settings)
    assert a.redacted.profile_sha256 == b.redacted.profile_sha256


async def test_runner_profile_sha_excludes_itself(settings: Settings) -> None:
    """The sha is computed over the model with `profile_sha256` excluded
    — otherwise it'd be self-referential and never settle."""
    result = await _run(FIXTURE_DIR / "bom.csv", settings)
    # 64 hex chars.
    assert len(result.redacted.profile_sha256) == 64
    assert all(c in "0123456789abcdef" for c in result.redacted.profile_sha256)
