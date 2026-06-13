# 🧪 RetrofitGPT evals — regression gate for the pipeline

A golden-case eval suite over the pipeline's **deterministic decision layer**. It
pins each golden building's business case (savings / payback / NPV / carbon
**bands**) plus its **GL14 calibration verdict** and **NCC Section J verdicts**, so
none can silently drift.

## Why this exists (the interview line)

> *"The eval suite is the gate that makes the DeepSeek↔Claude provider swap safe to
> flip — the numbers and governance verdicts have to stay inside their bands no
> matter which model runs the judgement nodes. It also locks the 7 'green-but-wrong'
> bugs out: one case is a negative control that proves the GL14 gate still rejects an
> uncalibrated model."*

## Two tiers

| Tier | What runs | Needs | Role |
|------|-----------|-------|------|
| **A** (default) | real `analyse()` / `review()` / NCC checks over canned sim fixtures | nothing (CI / sandbox) | the regression gate |
| **B** (`--live`) | the real LLM-judgement nodes (`retriever._classify`, `modeler._select_measures`) against the configured provider | a provider key (NO EnergyPlus/Docker) | **gates the DeepSeek↔Claude swap** |

Tier A is deliberately deterministic so it runs anywhere and is fast. Tier B answers
the swap question — *does the new model classify the building, pick the right
measures, emit valid JSON, and stay stable?* — by calling the judgement functions
directly with canned IDF metadata and the real provider. Because those functions are
pure (injected `llm`), Tier B needs **no EnergyPlus and no Docker** — it isolates the
one variable being gated (the model) and stubs the physics.

### What Tier B checks (provider-invariant specs)

1. `classify.building_type` ∈ the allowed set; HVAC summary non-empty.
2. `select` ⊆ catalog, count ≥ min, and `must_include` measures present.
3. **`llm_parsed`** — the model's raw output was valid strict-JSON, *not* the silent
   fallback. The agents swallow a bad LLM response into a deterministic fallback
   (right for production), which would otherwise **mask** a model that can't emit
   JSON — so the swap gate verifies the model itself produced usable output.
4. **stability** across `--samples N` — `building_type` identical, measure-set
   Jaccard ≥ threshold. Catches a model that flip-flops.
5. **citation judgement** (Reviewer-class, `verification.guardrails.judge_claims_grounded`)
   — a clean business case must read as `supported`; a version with a fabricated,
   uncited claim (an invented rebate / grant / guarantee) must read as `unsupported`.
   This is the nuance the deterministic number-matcher can't catch, and exactly what
   must survive a swap. Fail-closed: a judge that can't emit JSON fails both checks.

The report records the **provider, model id, and token usage** (the cost signal for
the swap decision). A missing key or unreachable provider fails with a clear message
— never disguised as a model-quality regression.

## Run it

```bash
# Tier A — deterministic gate (CI / sandbox, no key)
python3 evals/run_evals.py                      # all cases → report + exit code
python3 evals/run_evals.py --case doe_small_office_demo
python3 evals/run_evals.py --json               # machine-readable summary
pytest tests/test_evals.py tests/test_evals_tierB.py   # both gates in the suite

# Tier B — live model-swap gate (needs a provider key; run on your machine)
python3 evals/run_evals.py --live --samples 3   # uses LLM_PROVIDER from .env
LLM_PROVIDER=deepseek python3 evals/run_evals.py --live   # gate the swap target
LLM_PROVIDER=anthropic python3 evals/run_evals.py --live  # baseline
```

To gate a swap: run Tier B once under `anthropic` and once under `deepseek`; both
must stay green (and compare the token usage the report prints).

Exit `0` = every assertion passed. Exit `1` = a regression. Reports land in
`evals/results/` (`latest.json`, `latest.md`, plus a timestamped copy).

## Cases (`test_cases/*.json`)

- **`doe_small_office_demo`** — happy path. Pins LED ≈16.9% savings / ~4.3 yr,
  efficient-equipment ~11.1% / ~4.0 yr, recommended = `efficient_equipment`,
  GL14 approved, and NCC verdicts (baseline 10.76 W/m² → non-compliant, LED 4.5 →
  compliant, plug loads → not_regulated, glazing → requires_calculation, plus the
  **aggregate area-weighted** floor check).
- **`medium_office`** (Melbourne, zone 6, 3000 m²), **`retail`** (Brisbane, zone 2,
  1500 m² — uses the NCC retail 14 W/m² limit), **`school`** (Canberra, zone 7,
  4000 m² — school learning-area 4.5 W/m²). Multi-archetype coverage so the gate
  isn't tuned to one building. All bands computed from the real analyzer output.
- **`uncalibrated_office_must_fail`** — negative control. Metered bills ~25% below
  the sim → Reviewer **must** withhold approval and route back to the Modeler.

Tier-A pins 5 cases (71 checks); Tier B runs the 4 with an `llm_expect` block.

## Add a golden case

Drop a JSON file in `test_cases/` with `id`, `description`, `building`,
`economics`, `sim` (baseline + scenarios with `annual_energy_kwh`, `annual_eui`,
`cost_aud`), a `calibration` mode (`demo` = bills synthesised from baseline,
`scaled` + `calibration_scale` = deliberately off), and an `expect` block of bands
and verdicts. `pytest` and `run_evals.py` pick it up automatically.

Bands (not exact values) are intentional: real EnergyPlus output has noise, so the
gate asserts membership in a defensible range, not bit-equality.
