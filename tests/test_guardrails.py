"""OWASP LLM06 (Excessive Agency) numeric guardrail.

The protection that matters for hiring credibility: a number can only appear in
the final report if the simulation actually produced it. These tests lock in the
parser (including the comma-grouping bug that was fixed) and the support check.
"""
from __future__ import annotations

from verification.guardrails import (
    enforce_llm06_guardrail, extract_numeric_claims,
)


# ── parser ──────────────────────────────────────────────────────────────────
def test_parser_handles_comma_grouped_decimal():
    # Regression: "4,050.0" must parse as 4050.0, NOT truncate to 405.
    assert extract_numeric_claims("saved 4,050.0 kWh") == [4050.0]


def test_parser_handles_millions_grouping():
    assert extract_numeric_claims("NPV of 1,234,567 AUD") == [1234567.0]


def test_parser_plain_decimal_and_negative():
    vals = extract_numeric_claims("payback 5.0 years, delta -13.2 tCO2e")
    assert 5.0 in vals and -13.2 in vals


# ── support check ───────────────────────────────────────────────────────────
def test_supported_claims_pass():
    allowed = [20.0, 6000.0, 5.0, 13.2]
    # Includes "tCO2e" to prove the CO2-digit fix end-to-end (no spurious 2.0).
    rec = "20% savings, 6000 AUD/yr, 5.0-year payback, 13.2 tCO2e"
    res = enforce_llm06_guardrail(rec, allowed)
    assert res["passed"] is True
    assert res["violations"] == []


def test_parser_ignores_digits_glued_to_letters():
    """Regression: the '2' in 'CO2' must NOT be read as the number 2.0,
    while a real adjacent number ('13.2') still parses correctly."""
    claims = extract_numeric_claims("13.2 tCO2e")
    assert 13.2 in claims
    assert 2.0 not in claims


def test_fabricated_number_is_flagged():
    allowed = [20.0, 6000.0]
    # 999.9 was never produced by the simulation → must be caught.
    res = enforce_llm06_guardrail("savings 6000 AUD but secretly 999.9", allowed)
    assert res["passed"] is False
    assert 999.9 in res["violations"]


def test_within_two_percent_tolerance_passes():
    # 6100 is within 2 % of a real 6000 (rounding) → allowed.
    assert enforce_llm06_guardrail("6100", [6000.0])["passed"] is True


def test_outside_tolerance_flagged():
    # 6200 is 3.3 % off 6000 → outside the 2 % tolerance.
    assert enforce_llm06_guardrail("6200", [6000.0])["passed"] is False


def test_ignore_small_skips_sub_unit_values():
    # 0.85 (e.g. a confidence score) is < 1, so ignore_small skips it even though
    # it isn't in allowed. Documents ACTUAL behaviour (threshold is abs<1).
    assert enforce_llm06_guardrail("confidence 0.85", [])["passed"] is True


def test_zero_is_supported_by_zero():
    res = enforce_llm06_guardrail("0", [0.0], ignore_small=False)
    assert res["passed"] is True
