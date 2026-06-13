# 🤝 RetrofitGPT — Session Handoff

> **Purpose:** single source of truth for picking this project up in a new chat.
> Read this first, then `PROJECT_MEMORY.md` (decisions + user context) and
> `RetrofitGPT_Project_Plan.md` (technical reference).
>
> **Last updated:** 12 June 2026 · **Build state:** Phase 1 ✅ · **Phase 2 COMPLETE — all 5 agents real, no stubs in the pipeline.** Live sim PASSED (EUI 133); Retriever verified live (zone 5). Suite **80 green**. Modeler live (inspect_idf + Claude) to verify on Taash's machine; then Phase 3 (RAG).

---

## 🎯 30-Second Summary

RetrofitGPT is an autonomous multi-agent system: upload a building energy model
(`.idf`) + 12 months of bills → it runs EnergyPlus retrofit simulations → outputs
an audit-ready decarbonisation business case (savings %, payback, tCO₂e, NPV),
verified against ASHRAE Guideline 14 calibration and an OWASP LLM06 guardrail.

- **Who:** Taash (Taashira Chikosi) — building-energy engineer (IESVE background), in school
- **Goal:** get hired in 🇦🇺 **Australia** (Big 4 sustainability / energy) while still studying
- **Market:** all data is Australian (NABERS, NCC Section J, CDR tariffs, NGA carbon factors, AUD)
- **Why it wins:** physics-in-the-loop + governance + cost discipline = senior-level hiring signal

---

## 🟢 REAL SIM RUNNER BUILT — now verify it live

The Docker image builds AND EnergyPlus runs. **Confirmed 10 Jun 2026:**
`docker compose run --rm app energyplus --version` → `EnergyPlus, Version 24.2.0-e7ecb2d53b`.

**Done this session (Agent 3, the physics agent):** `agents/sim_runner.py` —
the real Sim Runner now drives EnergyPlus **over the MCP protocol** (in-memory
FastMCP client, **Path A** — chosen so MCP is load-bearing, not decoration). It
orchestrates clone → modify → run → poll → extract per scenario and returns the
same `SimRunnerOutput` contract, so the Analyzer downstream is untouched.
Wired into `api/main.py` (line ~217, `await sim_runner_async(state)`); the stub
is no longer in the pipeline. **12 new pytest cases** (fake MCP client) — full
suite **48 green** in-sandbox.

**⚠️ Not yet proven on real physics** (EnergyPlus can't run in the assistant
sandbox). Two on-machine checks remain — see VERIFY THE SIM RUNNER below.

---

## ✅ What's BUILT and TESTED

| Layer | Status | Notes |
|-------|--------|-------|
| Repo scaffold + Docker + devcontainer | ✅ | image **builds** (EnergyPlus 24.2 under linux/amd64) |
| **20/20 MCP tools** (FastMCP) | ✅ | IDF (5), simulation (2), results (5), reference (4), analysis (4) |
| Pydantic schemas (all agent IO) | ✅ | `verification/pydantic_schemas.py` |
| ASHRAE GL14 calibration (NMBE, CV-RMSE) | ✅ **tested** | 8 pytest cases |
| OWASP LLM06 guardrail | ✅ **tested** | 10 cases; CO2-digit over-extraction bug **found + fixed** this session |
| Model router (DeepSeek + Claude) | ✅ | `router/model_router.py` — both keys wired |
| LangGraph supervisor + routing | ✅ | `agents/supervisor.py` |
| **Real Analyzer agent** | ✅ **tested** | 9 cases; savings/payback/NPV/carbon match hand-calcs |
| **Real Reviewer agent** | ✅ **tested** | 3 cases; deterministic gate + routing |
| FastAPI backend (REST + SSE + HITL) | ✅ | `api/main.py` — full stub pipeline runs end-to-end |
| **`/health` readiness probe** | ✅ **tested** | NEW — drives the site status dot; 3 cases |
| **Per-IP rate limiting** | ✅ **tested** | NEW — 429 cap on run creation; 3 cases |
| **Real Sim Runner agent** | ✅ **tested (fake client)** | NEW — `agents/sim_runner.py`; MCP-client orchestration; 12 cases; ⚠️ live EnergyPlus run still to confirm |
| **pytest suite + GitHub Actions CI** | ✅ **48 tests green** | `tests/`, `pytest.ini`, `.github/workflows/ci.yml` (+12 sim_runner) |
| Carbon factors (NGA 2025) | ✅ **primary-verified** | all 22 electricity + gas vs official DCCEEW XLSX |
| Next.js + assistant-ui frontend | ✅ scaffold | `frontend/` — Analysis + Dashboard pages |
| Demo buildings (DOE small + medium office) | ✅ committed | `data/reference_buildings/` (git-tracked) |

**Agents 1–2 (Retriever, Modeler) still run as stubs** (`agents/stubs.py`).
**Sim Runner, Analyzer, Reviewer are REAL.** Stub pipeline still runs end-to-end.

---

## 🔬 VERIFY THE SIM RUNNER (Taash, on your machine — 2 checks)

EnergyPlus only runs in Docker on your Mac mini, so these can't be done in-chat.

```bash
cd "/Users/taashchikosi/Documents/Claude/Projects/Agentic AI Portfolio/retrofitgpt"

# 0) make sure the Sydney weather file is present (writes the EPW the script needs)
python3 scripts/download_reference_data.py

# 1) libgomp1 / EnergyPlus runtime still good?
docker compose run --rm app energyplus --version
#    → expect: EnergyPlus, Version 24.2.0-e7ecb2d53b

# 2) LIVE PROOF — one real baseline sim through the MCP client → EnergyPlus
docker compose run --rm app python scripts/verify_sim_runner.py
#    → streams clone/run/poll/extract, prints a SimulationResult,
#      ends with "✅ PHYSICS LOOP CLOSED" (exit 0)
```

If step 2 prints **"IDF lacks Output:Meter,Electricity:Facility,Monthly"**, add
that line to `RefBldgSmallOffice.idf` and re-run — the monthly meter is what the
Reviewer's GL14 calibration consumes. That's the one likely snag; everything
else is wired. The in-sandbox suite (48 green) already proves the orchestration
logic; this proves the physics.

---

## 🗓️ Changelog — 12 June 2026

0e. **Real Modeler built (Agent 2) — PHASE 2 AGENTS COMPLETE.** `agents/modeler.py`:
   Claude selects retrofit measures from a seed catalog (`agents/retrofit_catalog.py`)
   given the BuildingContext; deterministic cost + NCC reference (`get_ncc_requirement`)
   + validates each measure's target type exists (`inspect_idf.object_types`). Targets
   use **wildcard** `object_name='*'` (building-wide), so retrofits apply without the
   LLM guessing object names — enhanced `modify_idf_component` to apply to all objects
   of a type. Backfills to ≥2 retrofits; raises if the model has no modifiable targets.
   9 tests (fake MCP + fake LLM). `scripts/verify_modeler.py` for live proof. Stub
   removed → **the whole pipeline is now real agents** (retriever→modeler→[HITL]→
   sim_runner→analyzer→reviewer). Suite **71 → 80 green**.

0d. **Retriever climate-zone bug fixed (live-found).** First live Retriever run
   returned `ncc_climate_zone: 1` — it read the US DOE prototype IDF's embedded
   `Site:Location` (+41.8°, Chicago) and the AU-latitude map fell through to zone 1.
   Fix: zone now sourced from project geography (explicit `building_location` →
   the Australian weather file `epw_path` → IDF latitude **guarded to −45..−9°**);
   added `state` param + state→zone map to `ncc_climate_zone`. Re-verified live: **zone 5
   (basis "state: NSW")**, EUI 126.4, live Claude HVAC summary. `floor_area_m2` still the
   transparent 511 fallback (DOE IDF autocalc geometry; `estimated:true`).

0c. **Real Retriever built (Agent 1)** — `agents/retriever.py`. Deterministic/LLM
   split: floor area (`inspect_idf`), `current_eui`, cost, and NCC climate zone are
   arithmetic/lookups; Claude (via router) sets ONLY `building_type` + `hvac_system`,
   schema-checked with a deterministic fallback. Extended `inspect_idf` to return
   `floor_area_m2` (sums ZONE Floor_Area×Multiplier; None if autocalc) + `location`.
   Added `ncc_climate_zone()` helper in `reference_tools` (city/lat → zone 1–8, seed,
   VERIFY). Wired into `api/main.py` (`await retriever_async`); stub removed. MCP +
   LLM both injectable → 8 tests (fake client + fake LLM). `scripts/verify_retriever.py`
   for live Docker+Claude proof. Suite **58 → 66 green**. ⚠️ `inspect_idf` floor-area
   + live Claude unverified in sandbox — run verify_retriever.py on the machine.

0b. **LLM provider switch** — `LLM_PROVIDER` in `.env` (`anthropic`=dev all-Claude ·
   `deepseek`=force all · unset=cost-tiered deploy). 5 router tests. Set to `anthropic`.

0a. **LIVE SIM RAN ✅ + results-extraction bug found & fixed.** First real
   EnergyPlus run (DOE small office, Sydney) completed in 18.4s — physics loop
   closed. But it reported **EUI 1498 kWh/m²/yr (~10x too high)** and a monthly
   profile of `[4.2, 4.2, …]`. Root cause in `mcp_server/tools/results_tools.py`
   (Phase-1 code, not the Sim Runner):
   - `get_annual_energy`/`get_eui` summed **every** `:Facility [J]` column —
     incl. `Source` (primary energy, 461,780), `EnergyTransfer`, `*Demand`, and
     `ElectricityPurchased/Net/Monthly` duplicates of `Electricity:Facility`.
   - `get_monthly_energy` read the **hourly** column's first 12 rows = first 12
     **hours** of Jan 1, not 12 months.
   **Fix:** extraction refactored into importable pure helpers (`annual_by_fuel`,
   `monthly_electricity_kwh`, `end_uses_kwh`, `_meter_col`, `_dedupe_sum_kwh`).
   Site energy now = `Electricity:Facility` + `NaturalGas:Facility` only; monthly
   reads the Monthly meter (dropna→12) with an hourly-resample fallback.
   **Verified on the real CSV: EUI 133.1, 12 real months summing to 64,586.7.**
   5 regression tests on a synthetic CSV reproducing the trap columns. ⚠️ Found
   by sanity-checking EUI against domain knowledge — a reminder that a green
   "success" is not a correct number. Re-run `scripts/verify_sim_runner.py` to
   see the corrected output end-to-end.

0. **Real Sim Runner built (Agent 3)** — `agents/sim_runner.py`:
   - **Path A chosen** (in-memory FastMCP client, real MCP protocol) over direct
     function calls, so MCP is load-bearing — the differentiating hiring signal.
   - Async orchestration (clone → modify → run → **poll** → extract) wrapped as
     `sim_runner_async` + a sync `sim_runner` for tests. Sequential scenarios
     (EnergyPlus under x86 emulation — no parallel thrash). Per-scenario SSE.
   - **Double-envelope unwrap** (`_unwrap`): strips MCP transport result + our
     `ToolResponse` wrapper → tool payload. Defensive across fastmcp versions.
   - Calibration guard: a sim that "succeeds" but yields ≠12 monthly values is
     marked **failed** (zeros, never faked) so GL14 can't be fed garbage.
   - Wired into `api/main.py` (`await sim_runner_async`); stub removed from path.
   - **12 pytest cases** (fake client) → suite **36 → 48 green**.
   - `scripts/verify_sim_runner.py` — on-machine live proof (one real sim).
   - Provider switch: `LLM_PROVIDER` in `.env` (`anthropic`=dev all-Claude ·
     `deepseek`=force all · unset=cost-tiered deploy default). 5 router tests.
     `.env` set to `anthropic` for building the Retriever/Modeler on Claude.

### Prior 10 June (AM) changelog

1. **Docker build fixed** (was failing all session):
   - Wrong EnergyPlus SHA `94a887817b` → corrected to verified **`e7ecb2d53b`**.
   - Arch mismatch: pinned **`platform: linux/amd64`** (EnergyPlus is x86_64-only; runs under emulation on the Apple-Silicon Mac mini).
   - Slow/flaky network: download now uses a **BuildKit cache mount** + `--http1.1 --retry -C -` so a dropped transfer **resumes across builds** instead of restarting 185 MB. Needs `# syntax=docker/dockerfile:1`.
   - Runtime lib: added **`libgomp1`** (separate layer, post-pip) — *pending verify*.
   - Added `.dockerignore` (keeps secrets/`node_modules` out of image).
2. **Carbon factors primary-verified** vs the official DCCEEW NGA Factors 2025 XLSX (Table 1) — all 8 grids × Scope 2/3 matched cell-by-cell; gas 0.185 kg/kWh confirmed via Table 5. Added a Scope 3 electricity block + WA SWIS/NWIS split.
3. **Test harness + CI** — 36 pytest cases across the deterministic layers; CI runs them on every push (no Docker needed). README badge added (replace `OWNER`).
4. **Guardrail bug fixed** — regex read the "2" in "CO2" as `2.0`; added a lookbehind + regression test.
5. **Sydney weather discovery fixed** — onebuilding.org has no station named "Sydney"; now discovers by stable WMO code **947670** (Sydney Airport) with fallbacks. Logic verified; live confirm on next run.
6. **OneSite integration contract** started — `/health` readiness probe + per-IP rate limit (both tested).

---

## 🚧 What's NOT done yet (next session picks up here)

1. **Verify the Sim Runner live** (see 🔬 VERIFY THE SIM RUNNER) — `libgomp1` check + `scripts/verify_sim_runner.py`. Code + 48 tests done; only the real-EnergyPlus run remains. *Needs Docker up.* **← do this first next session.**
2. ✅ **Real Retriever agent** — DONE this session (`agents/retriever.py`). RAG-sourced `applicable_codes` still deferred to Phase 3. Live `inspect_idf` floor-area + Claude classify unverified in sandbox → run `scripts/verify_retriever.py` in Docker.
3. ✅ **Real Modeler agent** — DONE (`agents/modeler.py` + `agents/retrofit_catalog.py`). Live `inspect_idf` + Claude unverified in sandbox → run `scripts/verify_modeler.py` in Docker. Catalog measures/costs are SEED (VERIFY). **← verify this next, then Phase 3 RAG.**
4. **Token cap** — hard per-run LLM token budget in `router/model_router.py` (per-call `max_tokens` + per-run total). Taash to pick the budget (~30–50k tokens/run starting point). *Abuse protection for the public agent.*
5. **RAG layer** (Phase 3) — ingest NCC Section J + NABERS into pgvector (free docs, user downloads; `data/codes/` gitignored).
6. **Tariff data** — `get_utility_rate` is a stub. Verify-fill it like the carbon factors: **upload the AER DMO 2025-26 determination spreadsheet** and confirm c/kWh + supply charges. (Real per-building tariff comes from the customer's bill; this is the fallback benchmark.) Live CDR Energy PRD API wiring is the later upgrade.
7. **Gas Scope 3** not yet in `nga_factors_2025.json` (extraction + distribution) — minor.
8. **Frontend ↔ backend live wiring** — SSE stream → agent-trace panel; the **pre-loaded auto-run** + **case-study page** at `/retrofitgpt`.
9. **Eval harness expansion** (Phase 3) — DeepEval cases beyond the deterministic suite.
10. **Deploy** (Phase 4) — see ONE-WEBSITE section: Vercel route + shared VPS container.

---

## 🌐 LOCKED decision — ONE unified portfolio website

**Do not re-open.** All agent projects (RetrofitGPT, AuditAgent, future) ship on
**one** site, not standalone:

- 🖥️ **Frontend** = one Next.js app on Vercel (free). RetrofitGPT's UI is a **route** (`/retrofitgpt`), not its own deployment.
- ⚙️ **Backend** = RetrofitGPT runs as a **containerised FastAPI service** on ONE shared always-on VPS (Hetzner/DO, ~$6–12/mo total) behind Caddy (TLS + reverse proxy), e.g. port `:8001`.
- 🗄️ **Shared infra** = ONE Postgres/pgvector + ONE Langfuse for all agents. Don't stand up private ones.

**RetrofitGPT integration contract (drop-in module):** containerised FastAPI ·
**`/health`** (✅ done) · **pre-loaded example + auto-run** · shared design system
(Tailwind + shadcn/ui + Framer Motion) · **rate-limit (✅) + token cap (todo)** ·
filled case-study page (hero + wow GIF + live embed + architecture diagram + eval
metrics + ADR + links). **Don't:** build a separate site/domain, deploy to a
sleeping free tier (no cold starts), use Framer/Webflow, or use private DB/Langfuse.
Source docs: `Portfolio_Demo_Site_Plan.md` + `HANDOFF_Project2_and_DemoSite.md`.

---

## 🔑 Credentials (all in `.env`, gitignored)

| Key | Status |
|-----|--------|
| `DEEPSEEK_API_KEY` | ✅ saved |
| `ANTHROPIC_API_KEY` | ✅ saved |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | ✅ saved (Tokyo: `jp.cloud.langfuse.com`) |

> ⚠️ Keys were pasted in chat — fine for now, rotate if ever exposed publicly.

---

## ⚠️ Known issues / gotchas

- **🐢 Taash's home network is very slow/flaky** (~12–50 KB/s observed). The first
  Docker build took ~54 min; the EnergyPlus + pip layers are now cached, so
  rebuilds are fast unless those layers are invalidated. If a download dies,
  **just re-run the build** — the cache mount resumes.
- **🍎 Apple Silicon + emulation** — always build via `docker compose` (which pins
  `platform: linux/amd64`), NOT plain `docker build` (which would build arm64 and
  EnergyPlus wouldn't run).
- **📦 Don't vendor the EnergyPlus tarball into the build context** — `vendor/` is
  gitignored and would break a fresh-clone deploy on the VPS. The cache-mount
  download is the correct cross-environment approach.
- **🌦️ Sydney weather** — re-run `python3 scripts/download_reference_data.py`; it
  now discovers the file by WMO code 947670. If it still can't, grab any
  `…947670…_TMYx.zip` from the onebuilding NSW index, unzip, place the `.epw` at
  `data/reference_buildings/weather/AUS_NSW_Sydney.epw`.
- **🐍 Host Python is 3.9** — host scripts need `from __future__ import annotations`
  for `X | None`. Docker uses 3.11; tests assume 3.10+.
- **📜 NCC lookups are seed data** (`get_ncc_requirement`) marked "VERIFY" — real
  values arrive with the RAG layer (Phase 3).
- **🛡️ Rate limiter is in-memory** (fine for single-container VPS; needs Redis if
  it ever scales horizontally) and trusts `X-Forwarded-For` (safe only because
  Caddy fronts it — don't expose the FastAPI port directly).
- **🔁 git** sometimes leaves `.git/HEAD.lock` — if a commit fails, `rm -f .git/HEAD.lock` then retry.
- **EnergyPlus can't run in the assistant's sandbox** — only on the user's machine
  via Docker. The agent tests the deterministic layers, not live sims.

---

## 🚀 How to run it (on Taash's machine)

```bash
cd "/Users/taashchikosi/Documents/Claude/Projects/Agentic AI Portfolio/retrofitgpt"

# 1) demo data (buildings committed; this grabs Sydney weather)
python3 scripts/download_reference_data.py

# 2) build + boot backend (first build ~50 min on slow net; rebuilds fast)
docker compose build app && docker compose run --rm app energyplus --version
docker compose up -d

# 3) run the test suite (no Docker needed)
pip install "pydantic>=2.0" pytest fastapi sse-starlette httpx
python -m pytest            # expect 36 passed

# 4) pre-cache baseline sims (instant-demo mode)
docker compose run --rm app python scripts/precache_baselines.py

# 5) frontend
cd frontend && npm install && npm run dev
# → http://localhost:3000   (backend: http://localhost:8080/docs , health: /health)
```

---

## 🗂️ Where things live

```
retrofitgpt/
├── Dockerfile             amd64 + cache-mount EnergyPlus download + libgomp1
├── docker-compose.yml     app (platform: linux/amd64) + pgvector db
├── .dockerignore          keeps secrets / node_modules out of the image
├── mcp_server/tools/      20 MCP tools (idf, simulation, results, reference, analysis)
├── agents/                supervisor + reviewer/analyzer (real) + stubs (1–4)
├── verification/          pydantic schemas, ashrae_checks, guardrails  ← all tested
├── router/                model_router.py (DeepSeek + Claude)  ← token cap goes here
├── api/main.py            FastAPI REST + SSE + HITL + /health + rate limit
├── tests/                 36 pytest cases (deterministic layers + /health + rate limit)
├── pytest.ini             pythonpath=. , testpaths=tests
├── .github/workflows/ci.yml   runs pytest on every push (badge in README)
├── frontend/              Next.js + assistant-ui (becomes a /retrofitgpt route)
├── data/                  reference_buildings/ (committed), factors/ (NGA, verified), codes/ (gitignored)
├── scripts/               download_reference_data.py, precache_baselines.py
├── PROJECT_MEMORY.md      decisions + user context (READ 2nd)
├── RetrofitGPT_Project_Plan.md   full technical spec (READ 3rd)
└── HANDOFF.md             ← you are here
```

---

## 🧠 How to work with Taash (critical)

- 🎨 Visual learner — diagrams, tables, structured layouts, emojis. **No walls of text.**
- 🧩 Systems thinker — give the full picture first, then steps.
- 🔬 Explain with **everyday analogies + concrete numbers** when she's stuck.
- 🗣️ She wants an **advisor, not a yes-man** — challenge assumptions, lead with the
  uncomfortable truth, tag confidence `[Certain]/[Likely]/[Guessing]`, never start
  with agreement, disagree with structure (reason → alternative → risk).
- 📣 **Narrate before each step** — one line on *what* + *why* before doing it.
- ✅ **Verify, don't assume** — primary sources over secondary; run the code; show the proof.
- 🎓 Cadence: **Build milestone → 🎓 visual learning session → 💼 LinkedIn post.**

---

## 📍 Recommended next action for the new session

> "Run the two checks in 🔬 VERIFY THE SIM RUNNER — `energyplus --version` then
> `scripts/verify_sim_runner.py`. Once it prints **✅ PHYSICS LOOP CLOSED**, the
> real Sim Runner is proven and Phase 2 just needs the **real Retriever +
> Modeler** against live DeepSeek. Then RAG (Phase 3). Tariffs unblock the moment
> Taash uploads the AER DMO spreadsheet. If the live run flags a missing monthly
> meter, add `Output:Meter,Electricity:Facility,Monthly;` to the demo IDF."

Confirm with Taash where she is before assuming — the build may already be verified.
