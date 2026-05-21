"""PII detection + stable placeholder redaction.

Plan §13 (PII handling); CHECKLIST.md lines 93-97. Two-tier detector:

- **High-confidence** rules (`email`, `phone`, `ip`, `national_id`,
  `cc_like`) set `pii_class` directly. `cc_like` additionally requires
  ≥ 50% of the sample to pass a Luhn check so it doesn't fire on random
  16-digit numbers.
- **Best-effort** rules (`name_like`, `address_like`) populate
  `pii_warnings` and leave `pii_class = none` — these are heuristics
  that the schema review UI should surface as warnings rather than
  treat as guarantees.

`redact_column(col)` is the **only** place the redacted-vs-raw artifact
split happens (plan §13 + `CLAUDE.md` "PII redaction is prompt-bound
only" invariant). Pure function; honors a `allow_raw` bool so the
worker can opt back into raw via `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`.
"""

from __future__ import annotations

import re
from typing import Any

from structai_core.profile.models import ColumnProfile, PiiClass, TopKEntry

# --- Public API ----------------------------------------------------------


def classify(
    *,
    pattern_hits: dict[str, float],
    values_sample: list[str],
    name: str,
    threshold: float = 0.9,
) -> tuple[PiiClass, list[str]]:
    """Returns `(pii_class, warnings)`. High-confidence rules set the
    class; best-effort rules append to warnings only."""

    if pattern_hits.get("email", 0.0) >= threshold:
        return PiiClass.email, []

    phone_hits = pattern_hits.get("phone_e164", 0.0) + pattern_hits.get("phone_us", 0.0)
    if phone_hits >= threshold:
        return PiiClass.phone, []

    ip_hits = pattern_hits.get("ip_v4", 0.0) + pattern_hits.get("ip_v6", 0.0)
    if ip_hits >= threshold:
        return PiiClass.ip, []

    if pattern_hits.get("national_id_us_ssn", 0.0) >= threshold:
        return PiiClass.national_id, []

    if pattern_hits.get("cc_luhn_format", 0.0) >= threshold:
        if values_sample:
            luhn_pass = sum(1 for v in values_sample if _luhn_check(v)) / len(values_sample)
            if luhn_pass >= 0.5:
                return PiiClass.cc_like, []

    warnings: list[str] = []
    if _is_name_like(name, values_sample):
        warnings.append("name_like")
    if _is_address_like(name, values_sample):
        warnings.append("address_like")
    return PiiClass.none, warnings


def redact_value(
    value: Any, pii_class: PiiClass, counter: dict[Any, int]
) -> Any:
    """Returns a stable `<EMAIL_N>`-style placeholder for `value`. Same
    raw value → same placeholder within `counter` (caller scopes per
    column). Pass-through if `pii_class == none` or the value is null."""

    if value is None or pii_class == PiiClass.none:
        return value
    label = _PLACEHOLDER_LABEL[pii_class]
    if value not in counter:
        counter[value] = len(counter) + 1
    return f"<{label}_{counter[value]}>"


def redact_column(col: ColumnProfile, *, allow_raw: bool = False) -> ColumnProfile:
    """Pure function. Returns a new ColumnProfile with sample_values,
    top_k.value, and outlier_examples rewritten when `col.pii_class !=
    none`. When `allow_raw` is True (the `STRUCTAI_ALLOW_RAW_LLM_SAMPLES`
    dev flag), returns a deep copy with no redaction applied."""

    new = col.model_copy(deep=True)
    if allow_raw or col.pii_class == PiiClass.none:
        return new

    counter: dict[Any, int] = {}
    new.sample_values = [
        redact_value(v, col.pii_class, counter) for v in new.sample_values
    ]
    if new.top_k:
        new.top_k = [
            TopKEntry(value=redact_value(t.value, col.pii_class, counter), count=t.count)
            for t in new.top_k
        ]
    if new.outlier_examples:
        new.outlier_examples = [
            redact_value(v, col.pii_class, counter) for v in new.outlier_examples
        ]
    return new


# --- Internals -----------------------------------------------------------

_PLACEHOLDER_LABEL = {
    PiiClass.email: "EMAIL",
    PiiClass.phone: "PHONE",
    PiiClass.ip: "IP",
    PiiClass.national_id: "NATIONAL_ID",
    PiiClass.cc_like: "CC",
}

_NAME_NAME_RE = re.compile(
    r"(first|last|full|given|family)[._\s]*name|^(first|last|full)$",
    re.IGNORECASE,
)
_ADDRESS_NAME_RE = re.compile(
    r"(addr|address|street|city|postal|zip)", re.IGNORECASE
)
_STREET_SUFFIX_RE = re.compile(
    r"\b(rd|st|ave|blvd|ln|dr|way|cir|ct)\b\.?", re.IGNORECASE
)


def _luhn_check(value: str) -> bool:
    s = re.sub(r"[\s\-]", "", value)
    if not s.isdigit() or not (13 <= len(s) <= 19):
        return False
    total = 0
    for i, c in enumerate(reversed(s)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_title_cased_words(value: str) -> bool:
    parts = value.strip().split()
    if not 2 <= len(parts) <= 3:
        return False
    for p in parts:
        if not p:
            return False
        if not p[0].isupper():
            return False
        if len(p) > 1 and not p[1:].islower():
            return False
    return True


def _is_name_like(name: str, sample: list[str]) -> bool:
    if _NAME_NAME_RE.search(name):
        return True
    if not sample:
        return False
    titles = sum(1 for v in sample if _is_title_cased_words(v))
    return titles / len(sample) >= 0.7


def _is_address_like(name: str, sample: list[str]) -> bool:
    if _ADDRESS_NAME_RE.search(name):
        return True
    if not sample:
        return False
    # At least 30% of values include a number and a street suffix.
    matches = sum(
        1
        for v in sample
        if re.search(r"\d", v) and _STREET_SUFFIX_RE.search(v) is not None
    )
    return matches / len(sample) >= 0.3
