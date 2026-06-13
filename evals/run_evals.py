"""RetrofitGPT regression eval harness (Tier A — deterministic, runs anywhere).

WHAT THIS IS
------------
A golden-case regression suite over the pipeline's DETERMINISTIC decision layer:
golden buildings → expected savings / payback / NPV / carbon BANDS + GL14 verdict
+ NCC Section J verdicts. It invokes the *real* production functions
(`agents.analyzer.analyse`, `agents.reviewer.review`, `verification.ncc_compliance`)
over canned simulation fixtures — so it pins behaviour without needing EnergyPlus
or a live LLM, and runs in CI / the assistant sandbox.

WHY IT MATTERS (the job signal)
-------------------------------
This is the gate that makes the DeepSeek↔Claude provider swap safe to flip: the
numbers and governance verdicts must stay inside their bands regardless of model.
It also locks the 7 "green-but-wrong" bugs out (e.g. case
`uncalibrated_office_must_fail` proves the GL14 gate still rejects an uncalibrated
model — the regression guard for the hourly-vs-monthly threshold bug).

  • Tier A (this file): deterministic layer, fixtures, no Docker. The regression gate.
  • Tier B (--live, on a real machine): re-run the golden cases through the real
    LLM-judgement nodes (Retriever classify / Modeler select / Reviewer citation)
    against the configured provider to gate the swap end-to-end. Hook is stubbed below.

USAGE
-----
    python3 evals/run_evals.py                 # run all cases, write reports, gate
    python3 evals/run_evals.py --case doe_small_office_demo
    python3 evals/run_evals.py --json          # machine-readable summary to stdout

Exit 0 = every assertion in every case passed. Exit 1 = at least one regression.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from agents.analyzer import analyse                              # noqa: E402
from agents.reviewer import review                               # noqa: E402
from verification.ncc_compliance import (                        # noqa: E402
    check_aggregate_lighting_compliance, check_lighting_power_density,
    check_ncc_compliance,
)
from verification.pydantic_schemas import (                      # noqa: E402
    SimRunnerOutput, SimulationResult,
)

CASES_DIR = Path(__file__).resolve().parent / "test_cases"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Sydney seasonal shape (summer-cooling peak) used to spread an annual kWh figure
# across 12 months so GL14 has realistic monthly structure to calibrate against.
_SEASONAL = [6800, 6500, 5900, 4900, 4300, 4100, 4200, 4400, 4700, 5300, 5900, 6500]
_SEASONAL_W = [w / sum(_SEASONAL) for w in _SEASONAL]
# Mean-neutral residuals (sum ≈ 0): NMBE ≈ 0, CV-RMSE ≈ 5% → inside GL14 monthly.
_DEMO_RESIDUALS = [+0.05, -0.05, +0.04, -0.04, +0.06, -0.06,
                   +0.05, -0.05, +0.04, -0.04, +0.06, -0.06]


@dataclass
class Check:
    name: str
    expected: object
    actual: object
    ok: bool


@dataclass
class CaseResult:
    case_id: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, expected, actual, ok: bool) -> None:
        self.checks.append(Check(name, expected, actual, ok))

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)


def _monthly(annual: float) -> list[float]:
    return [round(annual * w, 1) for w in _SEASONAL_W]


def _in_band(value: float, band: dict) -> bool:
    return band["min"] <= value <= band["max"]


def _fmt_band(band: dict) -> str:
    return f"[{band['min']}, {band['max']}]"


def _build_sim(case: dict) -> SimRunnerOutput:
    b = case["sim"]["baseline"]
    baseline = SimulationResult(
        scenario_name="baseline",
        annual_energy_kwh=b["annual_energy_kwh"],
        monthly_energy_kwh=_monthly(b["annual_energy_kwh"]),
        annual_eui=b["annual_eui"], simulation_status="success",
    )
    results = [baseline]
    for s in case["sim"]["scenarios"]:
        results.append(SimulationResult(
            scenario_name=s["name"],
            annual_energy_kwh=s["annual_energy_kwh"],
            monthly_energy_kwh=_monthly(s["annual_energy_kwh"]),
            annual_eui=s["annual_eui"], simulation_status="success",
        ))
    return SimRunnerOutput(results=results, baseline_result=baseline)


def _measured(case: dict, baseline_monthly: list[float]) -> list[float]:
    mode = case.get("calibration", "demo")
    if mode == "demo":
        return [round(k * (1 + r), 1) for k, r in zip(baseline_monthly, _DEMO_RESIDUALS)]
    if mode == "scaled":
        scale = case.get("calibration_scale", 1.0)
        return [round(k * scale, 1) for k in baseline_monthly]
    raise ValueError(f"unknown calibration mode: {mode}")


def run_case(case: dict) -> CaseResult:
    cr = CaseResult(case_id=case["id"])
    exp = case["expect"]
    econ = case["economics"]

    sim = _build_sim(case)
    costs = {s["name"]: s["cost_aud"] for s in case["sim"]["scenarios"]}

    analysis = analyse(
        sim=sim, scenario_costs=costs,
        tariff_aud_per_kwh=econ["tariff_aud_per_kwh"],
        carbon_factor_kg_per_kwh=econ["carbon_factor_kg_per_kwh"],
        tariff_source=econ["tariff_source"],
        emission_factor_source=econ["emission_factor_source"],
    )
    measured = _measured(case, sim.baseline_result.monthly_energy_kwh)
    rev = review(analysis, sim, measured)

    # ── Reviewer verdict ────────────────────────────────────────────────────
    cr.add("reviewer.approved", exp["reviewer_approved"], rev.approved,
           rev.approved == exp["reviewer_approved"])
    if "review_route_to" in exp:
        cr.add("reviewer.route_to", exp["review_route_to"], rev.route_to,
               rev.route_to == exp["review_route_to"])
    if "calibration_passed" in exp:
        cr.add("reviewer.calibration_passed", exp["calibration_passed"],
               rev.calibration_passed, rev.calibration_passed == exp["calibration_passed"])
    if "nmbe_pct" in exp:
        cr.add(f"reviewer.nmbe_pct in {_fmt_band(exp['nmbe_pct'])}",
               _fmt_band(exp["nmbe_pct"]), rev.nmbe_pct,
               rev.nmbe_pct is not None and _in_band(rev.nmbe_pct, exp["nmbe_pct"]))
    if "cvrmse_pct" in exp:
        cr.add(f"reviewer.cvrmse_pct in {_fmt_band(exp['cvrmse_pct'])}",
               _fmt_band(exp["cvrmse_pct"]), rev.cvrmse_pct,
               rev.cvrmse_pct is not None and _in_band(rev.cvrmse_pct, exp["cvrmse_pct"]))

    # ── Business case (only meaningful on approved cases) ─────────────────────
    if "recommended" in exp:
        cr.add("analyzer.recommended", exp["recommended"],
               analysis.recommended_package.scenario_name,
               analysis.recommended_package.scenario_name == exp["recommended"])
    if "total_carbon_reduction_tco2e" in exp:
        band = exp["total_carbon_reduction_tco2e"]
        v = analysis.total_carbon_reduction_tco2e
        cr.add(f"analyzer.total_carbon in {_fmt_band(band)}", _fmt_band(band), v, _in_band(v, band))

    by_name = {a.scenario_name: a for a in analysis.analyses}
    for name, bands in exp.get("analyses", {}).items():
        a = by_name.get(name)
        if a is None:
            cr.add(f"analyzer.{name}.present", "present", "MISSING", False)
            continue
        metric_map = {
            "savings_pct": a.energy_savings_pct,
            "payback_years": a.simple_payback_years,
            "carbon_tco2e": a.carbon_reduction_tco2e_per_year,
            "npv_aud": a.npv_aud,
        }
        for metric, band in bands.items():
            v = metric_map[metric]
            cr.add(f"analyzer.{name}.{metric} in {_fmt_band(band)}",
                   _fmt_band(band), v, _in_band(v, band))

    # ── NCC Section J verdicts ────────────────────────────────────────────────
    ncc = exp.get("ncc", {})
    for entry in ncc.get("lighting", []):
        r = check_lighting_power_density(entry["value_w_m2"],
                                         entry.get("space", "office_200lx_or_more"))
        cr.add(f"ncc.lighting.{entry['label']}", entry["status"], r["status"],
               r["status"] == entry["status"])
    for entry in ncc.get("components", []):
        r = check_ncc_compliance(entry["component"], entry.get("value"))
        cr.add(f"ncc.component.{entry['component']}", entry["status"], r["status"],
               r["status"] == entry["status"])
    if "aggregate" in ncc:
        agg = ncc["aggregate"]
        r = check_aggregate_lighting_compliance(agg["spaces"])
        cr.add(f"ncc.aggregate.{agg['label']}", agg["status"], r["status"],
               r["status"] == agg["status"])

    return cr


def _write_tier_b_reports(results: list, usage: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_at": ts, "tier": "B (live LLM judgement)",
        "provider": usage.get("provider"), "models": sorted(usage.get("models", set())),
        "tokens": {"input": usage.get("input", 0), "output": usage.get("output", 0)},
        "samples": usage.get("samples", 1),
        "total_cases": len(results),
        "passed_cases": sum(r.passed for r in results),
        "cases": [
            {"id": r.case_id, "passed": r.passed,
             "checks": [{"name": c.name, "expected": c.expected,
                         "actual": c.actual, "ok": c.ok} for c in r.checks],
             "samples": r.samples}
            for r in results
        ],
    }
    (RESULTS_DIR / "latest_tierB.json").write_text(json.dumps(payload, indent=2, default=str))
    (RESULTS_DIR / f"{ts}_tierB.json").write_text(json.dumps(payload, indent=2, default=str))

    md = [f"# RetrofitGPT eval run (Tier B) — {ts}", "",
          f"Provider: **{payload['provider']}** · models: {payload['models']} · "
          f"samples/case: {payload['samples']} · tokens in/out: "
          f"{payload['tokens']['input']}/{payload['tokens']['output']}", "",
          f"**{payload['passed_cases']}/{payload['total_cases']} cases passed.**", ""]
    for r in results:
        icon = "✅" if r.passed else "❌"
        n_ok = sum(c.ok for c in r.checks)
        md.append(f"## {icon} {r.case_id} ({n_ok}/{len(r.checks)})")
        md.append("")
        md.append("| ok | check | expected | actual |")
        md.append("|----|-------|----------|--------|")
        for c in r.checks:
            md.append(f"| {'✓' if c.ok else '✗'} | {c.name} | `{c.expected}` | `{c.actual}` |")
        md.append("")
    (RESULTS_DIR / "latest_tierB.md").write_text("\n".join(md))
    return RESULTS_DIR / "latest_tierB.md"


def run_tier_b(cases: list[dict], samples: int) -> int:
    """Tier B: gate the LLM-judgement layer against the configured provider.

    Builds real model-router wrappers (Retriever/Modeler task types), runs only the
    cases that carry an `llm_expect` block, and reports model + token usage.
    """
    import os

    from evals.tier_b import run_case_tier_b

    live_cases = [c for c in cases if "llm_expect" in c]
    if not live_cases:
        print("⚠️  No cases carry an `llm_expect` block — nothing for Tier B to run.")
        return 2

    usage = {"provider": os.environ.get("LLM_PROVIDER", "auto"),
             "models": set(), "input": 0, "output": 0, "samples": samples}

    # Preflight: the agent LLM nodes swallow any provider error into a deterministic
    # fallback (right for production resilience, but it would disguise "the model
    # never ran" as "the model gave a bad answer"). So verify the needed API key(s)
    # are present BEFORE running, and fail with a clear message if not.
    from router.model_router import route_task
    needed = {route_task("retrieval", 0.0).provider,
              route_task("modelling", 0.6).provider}
    keyvar = {"anthropic": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
    missing = [keyvar[p] for p in needed if not os.environ.get(keyvar[p])]
    if missing:
        print(f"💥 Tier B can't run: missing {', '.join(missing)} for provider(s) "
              f"{sorted(needed)} (LLM_PROVIDER={usage['provider']}).\n"
              f"   Tier B needs a real provider — set the key(s) in .env and run on a "
              f"machine with network access (not the assistant sandbox).")
        return 1

    # Direct probe — call the provider ONCE outside the agent nodes so the REAL error
    # surfaces. The judgement nodes swallow any failure into a deterministic fallback
    # (right for production), which otherwise hides whether the cause is a missing SDK
    # package, a bad key, or no network.
    from router.model_router import complete
    try:
        complete("retrieval", "Reply with the single word OK.", "ping", max_tokens=5)
    except ModuleNotFoundError as exc:
        pkg = {"anthropic": "anthropic", "deepseek": "openai"}
        want = sorted({pkg[p] for p in needed})
        print(f"💥 Tier B can't reach the provider — missing Python package "
              f"({type(exc).__name__}: {exc}).\n"
              f"   Install it:  pip3 install {' '.join(want)}\n"
              f"   (Provider {sorted(needed)} needs that SDK installed in this python3.)")
        return 1
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if any(w in msg for w in ("auth", "401", "api key", "invalid", "permission")):
            why = "the API key looks invalid/expired — check the value in .env"
        elif any(w in msg for w in ("connect", "timeout", "network", "resolve", "ssl")):
            why = "looks like a network/firewall issue — check this machine's connection"
        else:
            why = "see the error above"
        print(f"💥 Tier B can't reach the provider: {type(exc).__name__}: {exc}\n"
              f"   → {why}.")
        return 1

    def _make_wrapper(task_type: str, complexity: float):
        from router.model_router import complete

        def _fn(system: str, user: str) -> str:
            r = complete(task_type, system, user, complexity=complexity, max_tokens=300)
            usage["models"].add(r.get("model"))
            usage["input"] += r.get("usage", {}).get("input", 0)
            usage["output"] += r.get("usage", {}).get("output", 0)
            return r["text"]
        return _fn

    llm_classify = _make_wrapper("retrieval", 0.0)
    llm_select = _make_wrapper("modelling", 0.6)
    llm_judge = _make_wrapper("verification", 0.0)   # Reviewer-class citation review

    results = []
    try:
        for c in live_cases:
            results.append(run_case_tier_b(c, llm_classify, llm_select,
                                           samples=samples, llm_judge=llm_judge))
    except Exception as exc:  # noqa: BLE001 — surface a missing key / network clearly
        print(f"💥 Tier B could not reach the provider: {type(exc).__name__}: {exc}\n"
              f"   Set LLM_PROVIDER + the matching API key in .env and run on a machine "
              f"with network access (not the assistant sandbox).")
        return 1

    # If the key was present but no call actually succeeded (bad key / no network),
    # every judgement fell back — surface that as a connectivity problem, not a
    # model-quality regression.
    if not usage["models"] and usage["input"] == 0:
        print("💥 Tier B reached no model — every call fell back (invalid key or no "
              "network?). This is a connectivity failure, not a model regression. "
              "Check the provider key and network on this machine.")
        return 1

    report = _write_tier_b_reports(results, usage)
    _print_report(results)
    passed, total = sum(r.passed for r in results), len(results)
    bar = "─" * 60
    print(f"\n{bar}")
    verdict = "✅ ALL GREEN" if passed == total else "❌ REGRESSION DETECTED"
    print(f"  {verdict} — Tier B {passed}/{total} cases (provider={usage['provider']}, "
          f"models={sorted(usage['models'])}, {samples} samples/case)")
    print(f"  Tokens in/out: {usage['input']}/{usage['output']}  ·  Report: {report}")
    print(bar)
    return 0 if passed == total else 1


def _load_cases(only: str | None) -> list[dict]:
    files = sorted(CASES_DIR.glob("*.json"))
    cases = [json.loads(f.read_text()) for f in files]
    if only:
        cases = [c for c in cases if c["id"] == only]
        if not cases:
            raise SystemExit(f"❌ no case with id '{only}' in {CASES_DIR}")
    if not cases:
        raise SystemExit(f"❌ no eval cases found in {CASES_DIR}")
    return cases


def _print_report(results: list[CaseResult]) -> None:
    for cr in results:
        icon = "✅" if cr.passed else "❌"
        n_ok = sum(c.ok for c in cr.checks)
        print(f"\n{icon} {cr.case_id}  ({n_ok}/{len(cr.checks)} checks)")
        for c in cr.checks:
            mark = "✓" if c.ok else "✗"
            line = f"   {mark} {c.name}"
            if not c.ok:
                line += f"   expected={c.expected!r} actual={c.actual!r}"
            print(line)


def _write_reports(results: list[CaseResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_at": ts, "tier": "A (deterministic)",
        "total_cases": len(results),
        "passed_cases": sum(r.passed for r in results),
        "cases": [
            {"id": r.case_id, "passed": r.passed,
             "checks": [{"name": c.name, "expected": c.expected,
                         "actual": c.actual, "ok": c.ok} for c in r.checks]}
            for r in results
        ],
    }
    (RESULTS_DIR / "latest.json").write_text(json.dumps(payload, indent=2, default=str))
    (RESULTS_DIR / f"{ts}.json").write_text(json.dumps(payload, indent=2, default=str))

    md = [f"# RetrofitGPT eval run — {ts}", "",
          f"Tier A (deterministic). **{payload['passed_cases']}/{payload['total_cases']} "
          f"cases passed.**", ""]
    for r in results:
        icon = "✅" if r.passed else "❌"
        n_ok = sum(c.ok for c in r.checks)
        md.append(f"## {icon} {r.case_id} ({n_ok}/{len(r.checks)})")
        md.append("")
        md.append("| ok | check | expected | actual |")
        md.append("|----|-------|----------|--------|")
        for c in r.checks:
            md.append(f"| {'✓' if c.ok else '✗'} | {c.name} | `{c.expected}` | `{c.actual}` |")
        md.append("")
    (RESULTS_DIR / "latest.md").write_text("\n".join(md))
    return RESULTS_DIR / "latest.md"


def main() -> int:
    p = argparse.ArgumentParser(description="RetrofitGPT regression eval harness")
    p.add_argument("--case", default=None, help="run only this case id")
    p.add_argument("--json", action="store_true", help="print machine-readable summary")
    p.add_argument("--live", action="store_true",
                   help="(Tier B) run the golden cases through the REAL LLM-judgement "
                        "nodes against the configured provider to gate the model swap. "
                        "Needs LLM_PROVIDER + an API key; no EnergyPlus/Docker required. "
                        "Run on a machine with network access, not the sandbox.")
    p.add_argument("--samples", type=int, default=3,
                   help="Tier B: judgement samples per case for the stability check "
                        "(default 3). Catches a model that flip-flops.")
    args = p.parse_args()

    # Load .env so `python3 evals/run_evals.py --live` picks up the provider key
    # WITHOUT Docker (Tier B's whole point is running outside the container).
    # docker-compose still injects .env via env_file; this makes the bare CLI behave
    # the same. Done here (not at import) so importing the module has no side effects.
    # python-dotenv is in requirements.txt; degrade gracefully if it's absent.
    try:
        from dotenv import load_dotenv
        load_dotenv(_REPO_ROOT / ".env")
    except ImportError:  # pragma: no cover — fall back to a shell `export`/`source`
        pass

    cases = _load_cases(args.case)

    if args.live:
        return run_tier_b(cases, samples=args.samples)

    results = [run_case(c) for c in cases]
    report_path = _write_reports(results)

    passed = sum(r.passed for r in results)
    total = len(results)

    if args.json:
        print(json.dumps({"passed_cases": passed, "total_cases": total,
                          "all_passed": passed == total}, indent=2))
    else:
        _print_report(results)
        bar = "─" * 60
        print(f"\n{bar}")
        verdict = "✅ ALL GREEN" if passed == total else "❌ REGRESSION DETECTED"
        print(f"  {verdict} — {passed}/{total} golden cases passed")
        print(f"  Report: {report_path}")
        print(bar)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
