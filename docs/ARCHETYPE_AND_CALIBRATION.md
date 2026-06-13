# 🏢 Building Archetype & Calibration — what model we use, why, and how we'd calibrate for real

> **TL;DR** — RetrofitGPT's demo runs on the **DOE Commercial Reference Small
> Office** prototype, re-located to Sydney. It is a *representative archetype*,
> not a model of any specific building. Our calibration gate (ASHRAE Guideline 14)
> therefore can't pass on real metered bills until the model is **tuned to a
> specific building**. The `--calibrate-demo` flag produces a green run by
> synthesising bills from the baseline sim — a **pipeline proof, not a real
> calibration**. This doc explains the decision and the real tuning workflow.

---

## 1. 🧩 The model we use

| | |
|---|---|
| **Archetype** | DOE Commercial Prototype — **Small Office** (`RefBldgSmallOffice.idf`) |
| **Floor area** | ~511 m² (single storey, 5 thermal zones + plenum) |
| **Source** | US DOE / PNNL commercial reference building set (public, EnergyPlus-native) |
| **Climate** | Re-pointed to **Sydney** via `AUS_NSW_Sydney.epw`; NCC climate zone 5 |
| **Baseline result** | EUI **133.1 kWh/m²·yr** (~68,003 kWh/yr) from a real EnergyPlus run |

---

## 2. 🤔 Why a generic prototype (and not a real building)

The decision, and the trade-off behind it:

- ✅ **Reproducible & public.** Anyone can run the exact same model — no private
  building data, no NDA, no consent issues. Essential for an open portfolio piece.
- ✅ **EnergyPlus-native & calibrated archetype.** DOE prototypes are widely used
  as the *baseline* in research and code-development; they're a credible starting
  point that a reviewer will recognise instantly.
- ✅ **Proves the system, not a single building.** The portfolio claim is *"I built
  an autonomous multi-agent pipeline that drives real EnergyPlus simulations and
  governs its own outputs"* — that's demonstrated regardless of which building loads.
- ⚠️ **The cost:** a generic prototype is **not** any real building. Its schedules,
  plug loads, occupancy and HVAC efficiency are archetype defaults. So its
  simulated energy will **not** match a real building's bills out of the box —
  which is exactly why the calibration gate matters (see §3).

> 🔑 **Interview line:** *"I deliberately demo on the DOE small-office prototype so
> the whole thing is reproducible and public. The moment you point it at a real
> building, my GL14 gate correctly refuses to sign off until the model is tuned —
> that's the governance layer doing its job, not a bug."*

---

## 3. 🚦 Why real bills don't calibrate to the prototype (and that's correct)

Calibration (ASHRAE Guideline 14-2014 §5.2.2) compares the **baseline sim's 12
monthly kWh** against the **measured utility bills**:

```
            ┌──────────────────────┐        ┌─────────────────────┐
 baseline → │ 12 monthly kWh (sim) │  ──►   │  GL14 monthly gate  │ ──► pass / fail
 bills    → │ 12 monthly kWh (real)│        │  |NMBE| ≤ 5 %       │
            └──────────────────────┘        │  CV-RMSE ≤ 15 %     │
                                            └─────────────────────┘
```

A real building's bills reflect **that** building's occupancy, equipment and
operation — none of which the generic prototype shares. So CV-RMSE blows past
15% and the gate **fails**. That failure is the system working: *an un-tuned
prototype is not a trustworthy model of your building, so don't build a business
case on it.*

> Thresholds are **resolution-dependent** (`verification/ashrae_checks.py`):
> monthly data → 5% / 15%; hourly data → 10% / 30%. Applying the hourly limit to
> monthly bills is a classic M&V error — we explicitly guard against it.

---

## 4. 🟢 The `--calibrate-demo` flag — a green path, honestly labelled

```bash
docker compose run --rm app python scripts/verify_pipeline.py --calibrate-demo
```

- After the baseline EnergyPlus sim, this **synthesises** the "measured" bills
  *from* the baseline monthly profile (+~5% fixed residual).
- Result: NMBE ≈ 0%, CV-RMSE ≈ 5% → calibration **passes** → Reviewer **approves**
  → the full business case prints on the green path.
- **It is circular by design.** The model is calibrated against its own output.
  It proves the *pipeline mechanics* of the approval path — it is **not** evidence
  that the model matches a real building. The run banner and final summary say so.

This exists so the green approval path is demonstrable on the reproducible
prototype, without faking a real calibration.

---

## 5. 🔧 How we'd calibrate to a REAL building (the iterative workflow)

This is the real M&V skill. Given one real building's 12 monthly bills:

```
 ① Match the archetype     pick the right prototype (office? retail? school?)
        │                  + right climate zone. Wrong archetype → never calibrates.
        ▼
 ② Set known facts         floor area, storeys, HVAC type, operating hours,
        │                  lighting/equipment power density from a walkthrough/audit.
        ▼
 ③ Run baseline sim        EnergyPlus → 12 monthly kWh.
        ▼
 ④ Compare to bills        compute NMBE + CV-RMSE (GL14 monthly).
        │
        ├─ pass (≤5% / ≤15%) ─────────────► ✅ calibrated — build the business case
        │
        └─ fail ─► ⑤ Tune the biggest driver, then loop to ③:
                      • occupancy + HVAC schedules (operating hours)
                      • plug-load / lighting power density
                      • infiltration / ventilation rates
                      • setpoints & equipment efficiency
                   Typically 3–8 iterations. Change ONE driver class at a time so
                   you can attribute the error reduction (don't tune blind).
```

- **Effort:** ~2–4 hours across a few passes, depending on how far the prototype
  starts from the real building.
- **Automation opportunity (Phase 3+):** this loop is itself agent-automatable —
  a "Calibrator" agent that proposes the next tuning move from the residual
  pattern (e.g. a uniform monthly offset → schedule/occupancy; summer-only
  over-prediction → cooling setpoint/efficiency). That's a strong future agent.

---

## 6. 🌐 FOR THE WEBSITE (surface at deploy)

When the portfolio site ships, include a short **"About the model"** panel on the
RetrofitGPT demo page so visitors aren't misled:

> **What you're seeing:** a live run on the **DOE Small Office reference building**
> (Sydney climate) — a representative archetype, not a specific building. The
> energy figures come from a **real EnergyPlus simulation**. The green calibration
> badge in this demo uses **synthetic bills derived from the baseline** to show the
> approval path; calibrating to a *real* building requires tuning the model to its
> actual bills (NMBE ≤ 5%, CV-RMSE ≤ 15%, ASHRAE Guideline 14). That tuning loop is
> the next milestone.

Design notes for the panel:
- 🏷️ A small **"Demo calibration"** badge next to the green verdict — never let the
  green imply a real-building calibration.
- 🔗 Link this badge to a short explainer (this doc, trimmed).
- 📊 Show the baseline EUI (133.1 kWh/m²·yr) and label units correctly (kWh/m²·yr,
  **not** MJ — that mislabel bit us once already).

---

*Related: `verification/ashrae_checks.py` (the gate), `scripts/verify_pipeline.py`
(`--calibrate-demo`), `Portfolio_Demo_Site_Plan.md` (deploy).*
