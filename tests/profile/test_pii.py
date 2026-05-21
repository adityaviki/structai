"""PII detector + redaction tests (CHECKLIST.md line 138)."""

from __future__ import annotations

import polars as pl

from structai_core.profile.models import (
    CardinalityClass,
    ColumnProfile,
    InferredType,
    PiiClass,
    TopKEntry,
)
from structai_core.profile.patterns import pattern_hits
from structai_core.profile.pii import (
    classify,
    redact_column,
    redact_value,
)


def _series(*values: str) -> pl.Series:
    return pl.Series("v", list(values), dtype=pl.Utf8)


# --- classify: high-confidence rules ----------------------------------


def test_classify_email_fires_high_confidence() -> None:
    s = _series(
        "alice@example.com", "bob@example.org", "carol@test.co",
        "dave@example.com", "eve@example.io",
    )
    hits = pattern_hits(s)
    cls, warnings = classify(pattern_hits=hits, values_sample=s.to_list(), name="email")
    assert cls == PiiClass.email
    assert warnings == []


def test_classify_phone_e164_fires() -> None:
    s = _series(
        "+14155551234", "+442071838750", "+819012345678",
        "+33145678901", "+919876543210",
    )
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="phone")
    assert cls == PiiClass.phone


def test_classify_ssn_fires() -> None:
    s = _series("123-45-6789", "987-65-4321", "555-12-3456", "111-22-3333", "222-33-4444")
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="ssn")
    assert cls == PiiClass.national_id


def test_classify_ipv4_fires() -> None:
    s = _series("192.168.1.1", "10.0.0.1", "172.16.0.5", "8.8.8.8", "1.1.1.1")
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="src_ip")
    assert cls == PiiClass.ip


def test_classify_cc_requires_luhn_to_pass() -> None:
    """Format matches + ≥ 50% Luhn pass → cc_like."""
    # All these are real Luhn-valid test card numbers.
    s = _series(
        "4242424242424242", "4111111111111111", "5555555555554444",
        "378282246310005", "6011111111111117",
    )
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="card_number")
    assert cls == PiiClass.cc_like


def test_classify_cc_format_only_does_not_fire() -> None:
    """16-digit numbers that all fail Luhn → not flagged."""
    # All Luhn-invalid (last digit shifted).
    s = _series(
        "4242424242424241", "4111111111111112", "5555555555554443",
        "1234567890123456", "9876543210987654",
    )
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="order_number")
    assert cls != PiiClass.cc_like


def test_classify_negative_pure_ints() -> None:
    s = _series("1", "2", "3", "4", "5")
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="id")
    assert cls == PiiClass.none


def test_classify_negative_free_text() -> None:
    s = _series("lorem ipsum", "dolor sit", "amet consectetur", "adipiscing elit")
    hits = pattern_hits(s)
    cls, _ = classify(pattern_hits=hits, values_sample=s.to_list(), name="description")
    assert cls == PiiClass.none


# --- classify: best-effort warnings -----------------------------------


def test_classify_name_like_by_column_name() -> None:
    s = _series("xyz1", "xyz2", "xyz3")
    cls, warnings = classify(
        pattern_hits={}, values_sample=s.to_list(), name="first_name"
    )
    assert cls == PiiClass.none
    assert "name_like" in warnings


def test_classify_name_like_by_sample_shape() -> None:
    s = _series("Alice Smith", "Bob Jones", "Carol Brown", "Dave White")
    cls, warnings = classify(
        pattern_hits={}, values_sample=s.to_list(), name="customer"
    )
    assert cls == PiiClass.none
    assert "name_like" in warnings


def test_classify_address_like_by_column_name() -> None:
    s = _series("aaa", "bbb", "ccc")
    cls, warnings = classify(
        pattern_hits={}, values_sample=s.to_list(), name="postal_code"
    )
    assert cls == PiiClass.none
    assert "address_like" in warnings


def test_classify_address_like_by_sample_shape() -> None:
    s = _series(
        "123 Main St", "456 Oak Ave", "789 Elm Blvd", "1001 Maple Rd",
    )
    cls, warnings = classify(
        pattern_hits={}, values_sample=s.to_list(), name="location"
    )
    assert cls == PiiClass.none
    assert "address_like" in warnings


# --- redact_value -----------------------------------------------------


def test_redact_value_stable_per_counter() -> None:
    counter: dict[object, int] = {}
    a1 = redact_value("alice@example.com", PiiClass.email, counter)
    b1 = redact_value("bob@example.com", PiiClass.email, counter)
    a2 = redact_value("alice@example.com", PiiClass.email, counter)  # same as a1
    assert a1 == "<EMAIL_1>"
    assert b1 == "<EMAIL_2>"
    assert a2 == a1


def test_redact_value_passthrough_for_none_class() -> None:
    counter: dict[object, int] = {}
    out = redact_value("anything", PiiClass.none, counter)
    assert out == "anything"


def test_redact_value_passthrough_for_null() -> None:
    counter: dict[object, int] = {}
    out = redact_value(None, PiiClass.email, counter)
    assert out is None


def test_redact_value_per_class_label() -> None:
    for cls, label in [
        (PiiClass.email, "EMAIL"),
        (PiiClass.phone, "PHONE"),
        (PiiClass.ip, "IP"),
        (PiiClass.national_id, "NATIONAL_ID"),
        (PiiClass.cc_like, "CC"),
    ]:
        counter: dict[object, int] = {}
        out = redact_value("x", cls, counter)
        assert out == f"<{label}_1>"


# --- redact_column ----------------------------------------------------


def _col(*, pii_class: PiiClass, samples, top_k=None) -> ColumnProfile:
    return ColumnProfile(
        name="email", safe_name="email", position=0,
        inferred_type=InferredType.string, null_count=0, null_rate=0.0,
        distinct_count=len(samples), cardinality_class=CardinalityClass.low,
        sample_values=list(samples),
        top_k=top_k,
        pii_class=pii_class, pk_score=0.5,
    )


def test_redact_column_rewrites_samples_and_top_k() -> None:
    col = _col(
        pii_class=PiiClass.email,
        samples=["alice@example.com", "bob@example.com", "alice@example.com"],
        top_k=[
            TopKEntry(value="alice@example.com", count=10),
            TopKEntry(value="bob@example.com", count=5),
        ],
    )
    red = redact_column(col)
    # Same raw maps to same placeholder across both surfaces.
    assert red.sample_values[0] == red.sample_values[2]
    assert red.sample_values[0] != red.sample_values[1]
    # top_k value uses the same N as the corresponding sample.
    top_alice = red.top_k[0].value
    top_bob = red.top_k[1].value
    assert top_alice == red.sample_values[0]
    assert top_bob == red.sample_values[1]
    # Counts are unchanged.
    assert red.top_k[0].count == 10
    assert red.top_k[1].count == 5


def test_redact_column_none_class_is_identity() -> None:
    col = _col(
        pii_class=PiiClass.none,
        samples=["alice", "bob"],
    )
    red = redact_column(col)
    assert red.sample_values == ["alice", "bob"]
    # New object, but same content.
    assert red is not col


def test_redact_column_allow_raw_skips_redaction() -> None:
    col = _col(
        pii_class=PiiClass.email,
        samples=["alice@example.com", "bob@example.com"],
    )
    red = redact_column(col, allow_raw=True)
    assert red.sample_values == ["alice@example.com", "bob@example.com"]


def test_redact_column_does_not_mutate_input() -> None:
    col = _col(
        pii_class=PiiClass.email,
        samples=["alice@example.com"],
    )
    _ = redact_column(col)
    assert col.sample_values == ["alice@example.com"]
