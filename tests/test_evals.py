"""Fold the golden-case eval harness into the test suite (CI regression gate).

`pytest` now fails if any golden building drifts outside its expected savings /
payback / carbon bands or its cohort-realism + NCC verdicts change. This is the gate that
keeps the DeepSeek↔Claude swap honest at the deterministic layer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.run_evals import _load_cases, run_case

CASES = _load_cases(None)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_case_passes(case):
    result = run_case(case)
    failed = [c.name for c in result.checks if not c.ok]
    assert result.passed, f"{case['id']} regressed: {failed}"


def test_negative_control_actually_exercises_the_gate():
    """The out-of-cohort case must FAIL the realism gate and route back to the
    INPUTS — proving the CBD-cohort gate isn't a rubber stamp."""
    case = next(c for c in CASES if c["id"] == "baseline_outside_cohort_must_fail")
    result = run_case(case)
    checks = {c.name: c for c in result.checks}
    assert checks["reviewer.approved"].actual is False
    assert checks["reviewer.route_to"].actual == "inputs"


def test_every_case_file_has_required_fields():
    for f in (Path(__file__).resolve().parent.parent / "evals" / "test_cases").glob("*.json"):
        case = json.loads(f.read_text())
        for key in ("id", "description", "sim", "expect"):
            assert key in case, f"{f.name} missing '{key}'"
