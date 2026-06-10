"""OWASP LLM06 Excessive Agency guardrail (project plan §7).

Every numeric claim in a recommendation must trace to a simulation result.
Anything fabricated is rejected — the report can only state what EnergyPlus
actually produced.
"""
from __future__ import annotations

import re


class GuardrailViolation(Exception):
    pass


# Match either comma-grouped numbers (require ≥1 comma group) OR plain numbers.
# The comma-group alternative MUST require a comma (+), else "4050.0" gets
# truncated to "405" before the plain-number branch is tried.
_NUM = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")


def extract_numeric_claims(text: str) -> list[float]:
    out = []
    for tok in _NUM.findall(text):
        try:
            out.append(float(tok.replace(",", "")))
        except ValueError:
            continue
    return out


def _supported(claim: float, allowed: list[float], tol: float = 0.02) -> bool:
    """A claim is supported if it's within tolerance of a real simulated value."""
    for v in allowed:
        if v == 0:
            if abs(claim) < 1e-6:
                return True
        elif abs(claim - v) / abs(v) <= tol:
            return True
    return False


def enforce_llm06_guardrail(recommendation: str, allowed_values: list[float],
                            ignore_small: bool = True) -> dict:
    """Check every numeric claim against the set of real simulated values.

    allowed_values: every number the simulation legitimately produced
    (savings, EUI, payback, carbon, monthly kWh, etc.).
    Returns {passed, violations}. Raises GuardrailViolation on failure if strict.
    """
    violations = []
    for claim in extract_numeric_claims(recommendation):
        if ignore_small and abs(claim) < 1:   # skip years like "25-year", small ints
            continue
        if not _supported(claim, allowed_values):
            violations.append(claim)
    return {"passed": not violations, "violations": violations,
            "standard": "OWASP LLM Top 10 — LLM06 Excessive Agency"}
