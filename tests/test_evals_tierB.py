"""Tier B harness proof (sandbox, fake LLMs).

We can't call a live provider in the sandbox, so we prove the GATE itself: a good
provider passes, and every failure mode a model swap could introduce is caught —
wrong classification, broken JSON (masked by the agent fallback), a missing
must-have measure, and an unstable/flip-flopping model. The real provider runs on
Taash's machine via `python3 evals/run_evals.py --live`.
"""
from __future__ import annotations

import json

from evals.run_evals import _load_cases
from evals.tier_b import run_case_tier_b

# Pin to the office case by id (stable regardless of how many cases carry llm_expect).
CASE = next(c for c in _load_cases(None) if c["id"] == "doe_small_office_demo")


def good_classify(system, user):
    return '{"building_type": "small_office", "hvac_system": "VAV with reheat"}'


def good_select(system, user):
    return '{"measures": ["led_lighting", "efficient_equipment"], "rationale": "office"}'


def good_judge(system, user):
    # A working reviewer: flags the fabricated rebate/guarantee, passes the clean case.
    bad = any(w in user.lower() for w in ("rebate", "grant", "guarantee", "guaranteed"))
    verdict = "unsupported" if bad else "supported"
    return '{"verdict": "%s", "reason": "x"}' % verdict


def _failed(result):
    return [c.name for c in result.checks if not c.ok]


def test_good_provider_passes_all_checks():
    r = run_case_tier_b(CASE, good_classify, good_select, samples=3, llm_judge=good_judge)
    assert r.passed, _failed(r)


def test_wrong_building_type_is_caught():
    def bad(system, user):
        return '{"building_type": "hospital", "hvac_system": "VAV"}'
    r = run_case_tier_b(CASE, bad, good_select, samples=1)
    assert not r.passed
    assert any("building_type_allowed" in n for n in _failed(r))


def test_broken_json_classify_caught_by_parsed_check():
    # Agent falls back to small_office (which IS allowed) — but the model never
    # emitted valid JSON. The swap gate must still flag that.
    def broken(system, user):
        return "Sure! This looks like a small office building with VAV."
    r = run_case_tier_b(CASE, broken, good_select, samples=1)
    assert any("classify.llm_parsed" in n for n in _failed(r))


def test_broken_json_select_caught_by_parsed_check():
    def broken(system, user):
        return "I'd recommend LED lighting and more efficient equipment."
    r = run_case_tier_b(CASE, good_classify, broken, samples=1)
    assert any("select.llm_parsed" in n for n in _failed(r))


def test_missing_must_include_measure_is_caught():
    def sel(system, user):
        return '{"measures": ["efficient_equipment", "double_glazing"]}'
    r = run_case_tier_b(CASE, good_classify, sel, samples=1)
    assert any("must_include[led_lighting]" in n for n in _failed(r))


def test_flip_flopping_model_caught_by_stability():
    types = iter(["small_office", "medium_office", "small_office"])
    def flip(system, user):
        return json.dumps({"building_type": next(types), "hvac_system": "VAV"})
    r = run_case_tier_b(CASE, flip, good_select, samples=3)
    assert any("stability.classify" in n for n in _failed(r))


# ── citation judgement (Reviewer-class) ──────────────────────────────────────
def test_good_judge_passes_citation_checks():
    r = run_case_tier_b(CASE, good_classify, good_select, samples=1, llm_judge=good_judge)
    names = {c.name: c for c in r.checks}
    assert names["citation.clean→supported"].ok
    assert names["citation.tampered→unsupported"].ok


def test_judge_that_waves_through_fabrication_is_caught():
    # A weak reviewer that calls everything "supported" must FAIL the tampered check.
    def lax(system, user):
        return '{"verdict": "supported", "reason": "looks fine"}'
    r = run_case_tier_b(CASE, good_classify, good_select, samples=1, llm_judge=lax)
    assert any("citation.tampered" in n for n in _failed(r))


def test_broken_json_judge_caught_by_parsed_check():
    # Fail-closed: a judge that can't emit JSON fails BOTH citation checks.
    def broken(system, user):
        return "Yeah that all seems legit to me."
    r = run_case_tier_b(CASE, good_classify, good_select, samples=1, llm_judge=broken)
    failed = _failed(r)
    assert any("citation.clean" in n for n in failed)
    assert any("citation.tampered" in n for n in failed)


def test_citation_skipped_when_no_judge_supplied():
    # Without a judge, citation checks simply don't run (other checks still do).
    r = run_case_tier_b(CASE, good_classify, good_select, samples=1, llm_judge=None)
    assert not any("citation" in c.name for c in r.checks)
