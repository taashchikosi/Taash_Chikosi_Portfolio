# 🤖 Claude Code task — finish the multi-city scope (Medium + Large Office × 4 cities)

> **Context:** A prior session added a building+city selector to the Agentic Energy
> Modeller demo and wired the backend to be city-aware. The **code is done and
> tested** (142 backend tests green, frontend `tsc` clean). What's left needs a
> machine with real internet + the CBD register — i.e. you, running locally.
> This repo's remote is `github.com/taashchikosi/Taash_Chikosi_Portfolio`.

## ✅ Already done (do NOT redo)

| File | Change |
|---|---|
| `data/reference_buildings/catalog.json` | **NEW** — single source of truth: buildings (medium/large office) + cities (state, NCC zone, EPW name, grid factor). |
| `frontend/lib/energy-modeller-catalog.ts` | **NEW** — UI mirror of the catalog. `COHORTS` map holds verified benchmark medians. |
| `frontend/app/energy-modeller/demo.tsx` | Step-1 building + city selector + characteristics card; run payload now sends the selected IDF/EPW. |
| `api/main.py` | Emission factor now follows the **selected city's grid** (`_state_from_epw` + `carbon_factor_for_state`), not hardcoded NSW. |
| `scripts/download_reference_data.py` | Now fetches Large Office IDF + 4 city EPWs. |
| `scripts/build_cbd_cohorts.py` | Now builds **per-city** cohorts → keyed JSON. |
| `tests/test_city_carbon_factor.py` | **NEW** — 11 tests locking the per-city factor. |
| `docs/ARCHETYPE_AND_CALIBRATION.md` §1.5 | Documents the offices-only scope decision. |

**Scope is deliberately offices-only.** Don't add retail/hotel/hospital/etc. — the
CBD register (the only per-building AU benchmark) is office-only; non-office types
have no per-city cohort. Reasoning in `docs/ARCHETYPE_AND_CALIBRATION.md` §1.5.

## 📋 TODO (run locally, in order)

```bash
cd retrofitgpt   # the repo root (remote: Taash_Chikosi_Portfolio)

# 1. Fetch the Large Office IDF + the 4 city EPWs (sandbox couldn't reach the net).
python scripts/download_reference_data.py
#   → expect: RefBldgLargeOffice.idf, AUS_NSW_Sydney/ AUS_VIC_Melbourne/
#     AUS_QLD_Brisbane/ AUS_WA_Perth .epw in data/reference_buildings/weather/

# 2. Build the real per-city CBD cohorts. See docs/RUN_CBD_COHORTS.md for the
#    register download link. pandas + openpyxl required.
pip install pandas openpyxl
python scripts/build_cbd_cohorts.py --input ~/Downloads/cbd_register.csv
#   → writes data/benchmarks/cbd_office_cohorts.json; prints n/median per city.

# 3. Copy each VERIFIED cohort's {n, median} into the COHORTS map in
#    frontend/lib/energy-modeller-catalog.ts, keyed `${city}_${building}`.
#    Leave unverified (too-small) cohorts OUT — the UI shows "builds locally".
#    NOTE: a prior build had Sydney LARGE office at n=4 — large cohorts are sparse,
#    so some large-office cohorts may legitimately not verify. Don't fake them.

# 4. Verify.
python -m pytest tests/ -q
cd frontend && npx tsc --noEmit && npm run build
```

## 🔁 Then

- Smoke-test the demo: select each building × city, launch a live run, confirm the
  carbon number moves between cities (Perth lowest at 0.50, Melbourne highest 0.78).
- Commit + push (the working tree has many pre-existing untracked frontend files —
  stage deliberately, don't `git add -A` blindly).

## ⚠️ Folder check

Make sure you're in the repo whose remote is `Taash_Chikosi_Portfolio` (the prior
session edited `…/Agentic AI Portfolio/retrofitgpt/`). If a stale second copy
exists under a different path, ignore it — this repo is the source of truth.
