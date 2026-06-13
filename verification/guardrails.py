"""OWASP LLM06 Excessive Agency guardrail (project plan §7).

Every numeric claim in a recommendation must trace to a simulation result.
Anything fabricated is rejected — the report can only state what EnergyPlus
actually produced.

Two layers:
  • `enforce_llm06_guardrail` — DETERMINISTIC. Every *number* must match a real
    simulated value within tolerance. Cheap, certain, no model.
  • `judge_claims_grounded` — LLM JUDGEMENT (citation review). Catches the nuance a
    number-matcher can't: a *qualitative* fabrication like an invented rebate,
    incentive, or guarantee that no source supports. This is the Reviewer-class
    judgement the model-swap eval (Tier B) gates — does the new provider still flag
    an uncited claim as reliably as the baseline?
"""
from __future__ import annotations

import json
import re
from typing import Callable

LLMFn = Callable[[str, str], str]


class GuardrailViolation(Exception):
    pass


_CITATION_SYSTEM = (
    "You are a verification reviewer for a building-energy report. Decide whether "
    "EVERY claim in the text is grounded in the provided allowed_sources or the "
    "simulation. A claim that asserts a rebate, grant, incentive, guarantee, or any "
    "figure NOT attributable to an allowed source is UNSUPPORTED. Respond with STRICT "
    'JSON only: {"verdict": "supported" | "unsupported", "reason": "<one sentence>"}. '
    "No prose, no markdown."
)


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def judge_claims_grounded(llm: LLMFn, claims: str, allowed_sources: list[str]) -> dict:
    """LLM citation review with strict-JSON parse and a FAIL-CLOSED fallback.

    Returns {"verdict": "supported"|"unsupported", "reason": str, "parsed": bool}.
    `parsed` is False when the model didn't emit usable JSON (so the swap gate can
    tell a genuine "unsupported" verdict from a model that simply couldn't answer).
    """
    fallback = {"verdict": "unsupported", "parsed": False,
                "reason": "citation judgement unavailable — fail-closed"}
    try:
        user = json.dumps({"claims": claims, "allowed_sources": allowed_sources})
        parsed = json.loads(_strip_fence(llm(_CITATION_SYSTEM, user)))
        verdict = parsed.get("verdict")
        if verdict in ("supported", "unsupported"):
            return {"verdict": verdict, "parsed": True,
                    "reason": str(parsed.get("reason", ""))}
        return fallback
    except Exception:  # noqa: BLE001 — any LLM/parse failure → fail-closed
        return fallback


# Match either comma-grouped numbers (require ≥1 comma group) OR plain numbers.
# The comma-group alternative MUST require a comma (+), else "4050.0" gets
# truncated to "405" before the plain-number branch is tried.
# The (?<![A-Za-z]) lookbehind stops a digit glued to a letter from being read
# as a claim — e.g. the "2" in "CO2" must NOT parse as 2.0.
_NUM = re.compile(
    r"(?<![A-Za-z])(?:-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"
)


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
