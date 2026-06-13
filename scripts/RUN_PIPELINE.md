# ▶ Run the capstone — `verify_pipeline.py`

The end-to-end integration proof: all 5 real agents on one building, one command.

## Command (on your Mac mini)

```bash
cd "/Users/taashchikosi/Documents/Claude/Projects/Agentic AI Portfolio/retrofitgpt"

# once: fetch Sydney weather (skip if already done)
python3 scripts/download_reference_data.py

# the capstone (needs Docker — EnergyPlus + eppy live there)
docker compose run --rm app python scripts/verify_pipeline.py
```

First Docker build is slow on your home network (~50 min); rebuilds are cached.

## What it does

```
Retriever → Modeler → [HITL auto-approve] → Sim Runner → Analyzer → Reviewer
   ▲ calibration fail ──────────────────────────────────────────────┘
   (Reviewer routes back, max 3 cycles — mirrors supervisor.route_after_review)
```

- ONE shared in-memory FastMCP session drives Retriever, Modeler, Sim Runner.
- HITL gate is **auto-approved** (non-interactive run).
- ~3 real EnergyPlus sims (baseline + scenarios), ~1 min wall-clock.
- Prints: building context → scenarios → financial/carbon table → recommended
  package → Reviewer GL14 verdict.

## Expected outcome — read this before you panic at a ❌

The default bills are a **synthetic Sydney seasonal profile** (~66 MWh/yr), sized
to the DOE small-office baseline so GL14 calibration has a fair target. Two honest
outcomes, both = exit 0:

- **✅ Reviewer approved** — calibration + guardrail + citations all pass.
- **⚠️ Reviewer withheld approval** — most likely the synthetic bills don't match
  the baseline sim closely enough (NMBE/CV-RMSE out of GL14 bounds). This is the
  system **working correctly** — it refuses to sign off an uncalibrated model.

### Want a GREEN run today? Use `--calibrate-demo`

```bash
docker compose run --rm app python scripts/verify_pipeline.py --calibrate-demo
```

Synthesises the measured bills FROM the baseline sim so calibration passes
(NMBE ≈ 0%, CV-RMSE ≈ 5%) and the Reviewer approves — the full green approval
path. **Circular by design: a pipeline proof, NOT a real-building calibration.**
The run banner and summary say so. Full rationale + the real tuning workflow:
`docs/ARCHETYPE_AND_CALIBRATION.md`.

For a **true** calibration, pass real metered data:

```bash
docker compose run --rm app python scripts/verify_pipeline.py \
  --utility data/my_real_bills.json --tariff 0.32 --carbon-factor 0.66
```

`my_real_bills.json`: `{"monthly_kwh": [12 values], "annual_cost_aud": 19800, "tariff_type": "single rate"}`

## Interview framing

> "The capstone is one command that chains five agents over a shared MCP session:
> LLM-driven retrieval and measure selection, a human approval gate, real
> EnergyPlus simulation, deterministic financial maths, and a verification gate
> that runs ASHRAE Guideline-14 calibration and an OWASP-LLM06 guardrail — and
> **routes back** to re-model or re-analyse if a check fails. A withheld approval
> isn't a bug; it's the governance layer refusing to ship an uncalibrated number."

## If a stage raises

The script prints `💥 PIPELINE FAILED` with the stage, exception type, and full
traceback. Most likely causes, in order:
1. EnergyPlus not in the container → `docker compose run --rm app energyplus --version`
2. Missing Sydney EPW → re-run `download_reference_data.py`
3. `ANTHROPIC_API_KEY` / `LLM_PROVIDER=anthropic` missing from `.env`
