"""Tier B eval — gates the LLM-judgement layer across a provider swap.

Tier A pins the deterministic numbers. Tier B pins the part that ACTUALLY changes
when you flip DeepSeek↔Claude: the LLM judgement nodes —

    • Retriever  `_classify`        → building_type / hvac_system
    • Modeler    `_select_measures` → which catalog measures to propose

KEY DESIGN: these are pure functions taking an injected `llm`, so Tier B exercises
them directly with CANNED IDF metadata and the REAL provider. It needs NO EnergyPlus
and NO Docker — it isolates exactly the variable being gated (the model) and stubs
the physics. Runs on any machine with a provider key.

WHAT IT CHECKS (provider-invariant behavioural specs):
  1. classify.building_type ∈ allowed set; hvac non-empty.
  2. select ⊆ catalog; count ≥ min; must_include measures are present.
  3. PARSED — the raw model output was valid strict-JSON, not the silent fallback.
     (The agents swallow a bad LLM response into a deterministic fallback. That's
     right for production resilience but would MASK a model that can't emit JSON —
     so the swap gate verifies the model itself produced usable output.)
  4. STABILITY across N samples — building_type identical, measure-set Jaccard ≥
     threshold. Catches a model that flip-flops (a real DeepSeek-vs-Claude risk).

In-sandbox we prove this harness with injected fake LLMs (tests/test_evals_tierB.py);
the real provider runs on Taash's machine via `python3 evals/run_evals.py --live`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from agents.modeler import _select_measures, _strip_fence
from agents.retriever import _classify
from agents.retrofit_catalog import CATALOG
from verification.guardrails import judge_claims_grounded
from verification.pydantic_schemas import BuildingContext, UtilityData

LLMFn = Callable[[str, str], str]


@dataclass
class Check:
    name: str
    expected: object
    actual: object
    ok: bool


@dataclass
class TierBResult:
    case_id: str
    checks: list[Check] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)

    def add(self, name, expected, actual, ok) -> None:
        self.checks.append(Check(name, expected, actual, ok))

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)


def _classify_parsed(raw: str) -> bool:
    try:
        return bool(json.loads(_strip_fence(raw)).get("building_type"))
    except Exception:  # noqa: BLE001
        return False


def _select_parsed(raw: str) -> bool:
    try:
        keys = json.loads(_strip_fence(raw)).get("measures", [])
        return any(k in CATALOG for k in keys)
    except Exception:  # noqa: BLE001
        return False


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def _ctx(case: dict, building_type: str) -> BuildingContext:
    b = case["building"]
    return BuildingContext(
        building_type=building_type,
        floor_area_m2=float(b["floor_area_m2"]),
        ncc_climate_zone=int(b["ncc_climate_zone"]),
        hvac_system="(eval)", current_eui=case["sim"]["baseline"]["annual_eui"],
        annual_energy_cost_aud=0.0, idf_path="(eval)",
        utility_data=UtilityData(monthly_kwh=[1.0] * 12, annual_cost_aud=0.0),
    )


def run_case_tier_b(case: dict, llm_classify: LLMFn, llm_select: LLMFn,
                    samples: int = 1, llm_judge: LLMFn | None = None) -> TierBResult:
    """Run the LLM-judgement nodes `samples` times and score against `llm_expect`.

    `llm_classify` / `llm_select` / `llm_judge` are (system, user)->str. Live: the
    agents' real model-router wrappers. Tests: injected fakes. `llm_judge` drives the
    Reviewer-class citation review (skipped if the case has no `citation` spec).
    """
    spec = case["llm_expect"]
    meta = spec["idf_meta"]
    floor = float(meta.get("floor_area_m2", case["building"]["floor_area_m2"]))
    cr = TierBResult(case_id=case["id"])

    classify_types: list[str] = []
    select_sets: list[frozenset] = []

    for _ in range(max(1, samples)):
        # capture the raw classify response (to verify it actually parsed)
        raw_c = {}
        def cap_classify(system, user, _raw=raw_c):
            out = llm_classify(system, user)
            _raw["text"] = out
            return out
        cls = _classify(cap_classify, meta, floor)
        classify_types.append(cls["building_type"])

        ctx = _ctx(case, cls["building_type"])
        raw_s = {}
        def cap_select(system, user, _raw=raw_s):
            out = llm_select(system, user)
            _raw["text"] = out
            return out
        keys = _select_measures(cap_select, ctx)
        select_sets.append(frozenset(keys))

        cr.samples.append({
            "building_type": cls["building_type"], "hvac_system": cls["hvac_system"],
            "classify_parsed": _classify_parsed(raw_c.get("text", "")),
            "measures": sorted(keys),
            "select_parsed": _select_parsed(raw_s.get("text", "")),
        })

    # ── classify checks (first sample is representative; stability checked below)
    cspec = spec.get("classify", {})
    s0 = cr.samples[0]
    if "building_type_allowed" in cspec:
        allowed = cspec["building_type_allowed"]
        cr.add("classify.building_type_allowed", allowed, s0["building_type"],
               s0["building_type"] in allowed)
    if cspec.get("hvac_nonempty"):
        cr.add("classify.hvac_nonempty", "non-empty", s0["hvac_system"],
               bool(s0["hvac_system"]) and s0["hvac_system"] != "unknown")
    cr.add("classify.llm_parsed (not fallback)", True,
           all(s["classify_parsed"] for s in cr.samples),
           all(s["classify_parsed"] for s in cr.samples))

    # ── select checks
    sspec = spec.get("select", {})
    keys0 = set(cr.samples[0]["measures"])
    if sspec.get("subset_of_catalog"):
        cr.add("select.subset_of_catalog", "⊆ catalog", sorted(keys0),
               keys0.issubset(set(CATALOG)))
    if "min_count" in sspec:
        cr.add(f"select.count ≥ {sspec['min_count']}", sspec["min_count"],
               len(keys0), len(keys0) >= sspec["min_count"])
    for must in sspec.get("must_include", []):
        cr.add(f"select.must_include[{must}]", must, sorted(keys0), must in keys0)
    cr.add("select.llm_parsed (not fallback)", True,
           all(s["select_parsed"] for s in cr.samples),
           all(s["select_parsed"] for s in cr.samples))

    # ── stability across samples (only meaningful with samples > 1)
    stab = spec.get("stability", {})
    if samples > 1:
        modal = max(set(classify_types), key=classify_types.count)
        identical_pct = classify_types.count(modal) / len(classify_types)
        if "min_identical_classify_pct" in stab:
            cr.add(f"stability.classify ≥ {stab['min_identical_classify_pct']}",
                   stab["min_identical_classify_pct"], round(identical_pct, 2),
                   identical_pct >= stab["min_identical_classify_pct"])
        pairs = [(_jaccard(set(a), set(b)))
                 for i, a in enumerate(select_sets) for b in select_sets[i + 1:]]
        avg_j = sum(pairs) / len(pairs) if pairs else 1.0
        if "min_select_jaccard" in stab:
            cr.add(f"stability.select_jaccard ≥ {stab['min_select_jaccard']}",
                   stab["min_select_jaccard"], round(avg_j, 2),
                   avg_j >= stab["min_select_jaccard"])

    # ── citation judgement (Reviewer-class LLM06 nuance) ──────────────────────
    # A clean business case must read as SUPPORTED; a version with a fabricated,
    # uncited claim (e.g. an invented rebate) must read as UNSUPPORTED. This is the
    # judgement a number-matcher can't make — and exactly what must survive a swap.
    cit = spec.get("citation")
    if cit and llm_judge is not None:
        sources = cit.get("sources", [])
        clean = judge_claims_grounded(llm_judge, cit["clean_claim"], sources)
        cr.add("citation.clean→supported", "supported", clean["verdict"],
               clean["verdict"] == "supported" and clean["parsed"])
        tampered = judge_claims_grounded(llm_judge, cit["tampered_claim"], sources)
        cr.add("citation.tampered→unsupported", "unsupported", tampered["verdict"],
               tampered["verdict"] == "unsupported" and tampered["parsed"])

    return cr
