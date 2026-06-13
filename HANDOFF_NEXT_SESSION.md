# 🤝 RetrofitGPT — Session Handoff (pick up here in a new chat)

> **Read order:** this file first → `docs/ARCHETYPE_AND_CALIBRATION.md` (the model +
> calibration decision) → `HANDOFF.md` (full changelog history) →
> `RetrofitGPT_Project_Plan.md` (technical spec).
>
> **Date:** 12 June 2026 · **Build state:** Phase 1 ✅ · **Phase 2 COMPLETE — all 5
> agents real** · **Capstone E2E pipeline runs GREEN end-to-end** · **NCC Section J
> compliance is now REAL** (was hardcoded) · Test suite **93 green**.
>
> **What to do next:** §10. The two highest-leverage moves (evidence-backed) are an
> **evals harness** and a **live deployment**. Tier 2 NCC RAG is the natural Phase-3 brick.

---

## 1. 🎯 30-Second Summary

RetrofitGPT is an autonomous multi-agent system: upload a building energy model
(`.idf`) + 12 months of utility bills → it runs **real EnergyPlus** retrofit
simulations → outputs an audit-ready decarbonisation business case (savings %,
payback, tCO₂e, NPV), verified against **ASHRAE Guideline 14** calibration, an
**OWASP LLM06** guardrail, and **real NCC 2022 Section J** code compliance.

- **Who:** Taash (Taashira Chikosi) — building-energy engineer (IESVE background), studying.
- **Goal:** get hired in 🇦🇺 **Australia** (Big-4 sustainability / energy, or agentic-AI
  engineer / solution architect).
- **Market:** all data is Australian (NABERS, NCC Section J, NGA carbon factors, AUD).
- **Why it wins:** physics-in-the-loop **via MCP** + governance (calibration, guardrail,
  real code compliance) + cost discipline = senior-level hiring signal.

---

## 2. ✅ Current State — the whole pipeline is real AND runs end-to-end

```
 upload .idf + bills
        │
        ▼
   ┌─────────┐   ┌─────────┐   ┌──────────────┐   ┌────────────┐   ┌──────────┐   ┌──────────┐
   │Retriever│──▶│ Modeler │──▶│ HITL approve │──▶│ Sim Runner │──▶│ Analyzer │──▶│ Reviewer │──▶ business case
   │ Agent 1 │   │ Agent 2 │   │  (human gate)│   │  Agent 3   │   │  Agent 4 │   │  Agent 5 │
   └─────────┘   └─────────┘   └──────────────┘   └────────────┘   └──────────┘   └──────────┘
      REAL          REAL                              REAL             REAL           REAL
   inspect_idf   Claude picks                      EnergyPlus      $/payback/      GL14 calib +
   + Claude      measures +                        over MCP        NPV/tCO2e       LLM06 guardrail
   classify      REAL NCC J7D3                     (real sims)     (deterministic) (deterministic)
                 compliance check
                                                    Reviewer can route back:
                                                    calibration fail → Modeler
                                                    claim/citation fail → Analyzer (max 3 cycles)
```

| Agent | File | Status | Verified live? |
|-------|------|--------|----------------|
| 1 Retriever | `agents/retriever.py` | ✅ real | ✅ EUI 124.3, zone 5 |
| 2 Modeler | `agents/modeler.py` + `agents/retrofit_catalog.py` | ✅ real | ✅ LED+equipment, valid wildcard edits, REAL NCC check |
| 3 Sim Runner | `agents/sim_runner.py` | ✅ real | ✅ baseline EUI 133.1, real EnergyPlus ~14s |
| 4 Analyzer | `agents/analyzer.py` | ✅ real | ✅ deterministic |
| 5 Reviewer | `agents/reviewer.py` | ✅ real | ✅ GL14 + LLM06 deterministic |

**Capstone proof:** `scripts/verify_pipeline.py` chains ALL 5 agents on one building
over a single shared in-memory MCP session, auto-approves the HITL gate, honours the
Reviewer route-back loop, and prints the full business case + verdict. **Verified GREEN
on Taash's Mac (60s)** with `--calibrate-demo`: Reviewer APPROVED, NMBE +0.02%,
CV-RMSE 5.07%.

**Test suite: 93 passed** (no Docker — all use fakes). Run: `python3 -m pytest`.

---

## 3. 🆕 What changed THIS session (12 Jun 2026)

1. **Built the capstone E2E runner** `scripts/verify_pipeline.py` — the integration
   proof. Mirrors `api/main.py::_drive_pipeline` as a standalone CLI.
2. **`--calibrate-demo` flag** — synthesises "measured" bills FROM the baseline sim
   (+~5% fixed residual) so the GL14 gate passes and the green approval path runs on
   the un-tuned DOE prototype. **CIRCULAR BY DESIGN, loudly labelled** (banner +
   summary tag + flag help) as a pipeline proof, NOT a real-building calibration.
   Rationale + the real tuning workflow live in `docs/ARCHETYPE_AND_CALIBRATION.md`.
3. **Fixed GL14 thresholds (were wrong!)** — `verification/ashrae_checks.py` used
   NMBE ≤10% / CV-RMSE ≤30% labelled "monthly"; those are the **hourly** limits.
   Real **monthly** = 5% / 15%. Now **data-aware**: `resolution_limits(n)` →
   12=monthly(5/15), 8760/8784=hourly(10/30), else fail-closed.
4. **Made NCC Section J compliance REAL** (was hardcoded `code_compliance=True`).
   New `verification/ncc_compliance.py`, routed through the `get_ncc_requirement`
   MCP tool. Primary-verified against ABCB NCC 2022 J7D3, Table J7D3a.

### The 7 "green-but-wrong" bugs caught so far (the recurring lesson)

Each passed an automated check but was a wrong **number/claim** — caught only by
domain knowledge. **A green ✅ is not a correct value. Build that reflex.**

1. **Sim Runner EUI 1498 → 133** — `results_tools.py` summed every `:Facility`
   meter incl. `Source:Facility`. Fixed to site energy only.
2. **Retriever climate zone 1 → 5** — read the US prototype's embedded Chicago
   `Site:Location`. Fixed: zone from AU geography, latitude guarded to −45..−9°.
3. **Modeler target names** — stub targeted object names that don't exist → silent
   no-op. Fixed with wildcard `object_name='*'`.
4. **EnergyPlus field rename** — catalog used `Watts_per_Zone_Floor_Area`; E+ 24.2
   renamed it `Watts_per_Floor_Area` (Space concept dropped "Zone"). Hard crash.
   Fixed + hardened `modify_idf_component` to validate `field in obj.fieldnames`.
5. **EUI mislabel** — verify_pipeline printed kWh/m² values as "MJ/m²" (3.6× off).
   Values were consistent (kWh); label fixed.
6. **GL14 hourly-vs-monthly threshold** — see §3.3. Passed at CV-RMSE 17.7% (>15%
   monthly) because hourly limits were applied to monthly bills.
7. **Non-compliant LED claimed compliant** — catalog `led_lighting` targeted
   6.0 W/m² with `code_compliance=True`, but NCC office max is **4.5 W/m²**. Fixed
   catalog to 4.5; compliance is now a real check (see §6).

**Common thread of all 7:** *version-coupled or resolution-coupled or code-coupled
assumptions* baked in as constants. The fix is always: validate against the live
source (IDF fieldnames, data length, the actual NCC clause), don't hardcode.

---

## 4. 🏗️ Architecture

### MCP server (the physics/data layer)
- `mcp_server/server.py` — FastMCP server, **20 tools** across 5 groups (IDF,
  Simulation, Results, Reference, Analysis). Responses wrapped in a `ToolResponse`
  envelope (`schemas/tool_schemas.py::wrap()`).
- `get_ncc_requirement` is now a **real compliance tool** — calls
  `verification/ncc_compliance.py`. **Tier 2 (RAG over the live NCC) swaps this tool's
  internals; the agents never change.** This is the clean MCP boundary to show off.

### Agents
- Orchestrated by `agents/supervisor.py` (`RunState` TypedDict, LangGraph routing).
- **Reviewer routes back**: calibration fail → Modeler; claim/citation fail →
  Analyzer (max 3 cycles, then → human). See `route_after_review`.
- HITL interrupt sits **before** the Sim Runner.

### Model router + provider switch
- `router/model_router.py` — `complete(task_type, system, user, complexity, max_tokens)`.
- **`LLM_PROVIDER` env var** in `.env`: `anthropic` (dev, currently set) → all Claude;
  *(unset)* → DEPLOY default (cost-tiered, mostly DeepSeek, Claude only for the
  Reviewer gate). **At deploy: delete the `LLM_PROVIDER` line** (unset = smart default).
  The swap **must be eval-gated**, not blind.

---

## 5. 🧩 THE BUILD PATTERN (reuse for every new agent / check)

1. **Injectable MCP client** — reuse `FastMCPCaller` + `_unwrap` from
   `agents/sim_runner.py`. Tests inject a fake async callable returning canned dicts.
2. **Injectable LLM** — `LLMFn = Callable[[str, str], str]`. Default routes through
   `model_router.complete`; tests inject a fake.
3. **Async core + sync wrapper** — `<agent>_async(state, caller=None, llm=None)` is
   the real node; `<agent>(state, …)` is a sync `asyncio.run` wrapper for tests.
   **Never call the sync one from a running loop.**
4. **Deterministic/LLM split** — LLM only does judgement (classification, selection).
   Numbers/compliance are arithmetic/lookups with a deterministic fallback.
5. **Unit tests with fakes** — `tests/test_<agent>.py`.
6. **Live proof script** — `scripts/verify_<agent>.py`, run in Docker.

**Why injection matters:** the assistant sandbox **cannot** run EnergyPlus, eppy
(needs the IDD), or live LLM APIs (network-blocked). Logic is proven with fakes
in-sandbox; physics + live Claude are proven on Taash's Mac.

---

## 6. 🏛️ NCC Section J compliance — what's REAL now (the standout feature)

`verification/ncc_compliance.py` encodes **what the code actually regulates** — not a
naïve "value ≤ threshold" for everything:

| Component | NCC treatment | Status returned | Clause |
|-----------|---------------|-----------------|--------|
| Lighting power density | REGULATED, numeric | `compliant` / `non_compliant` | NCC 2022 J7D3, Table J7D3a |
| Equipment / plug loads | NOT regulated by Section J | `not_regulated` | J7 excludes GPO appliances |
| Glazing / fabric | Façade calculation (U×area+SHGC) | `requires_calculation` | NCC 2022 Part J4 |

**Primary-verified value:** office lit to ≥200 lx → **max 4.5 W/m²** (J7D3 Table J7D3a;
<200 lx → 2.5 W/m²). The catalog `led_lighting` now targets 4.5 (compliant). The DOE
baseline at 10.76 W/m² is itself **non-compliant** — a strong retrofit narrative.

`RetrofitScenario` gained `compliance_status` (Literal); `code_compliance` bool stays
(== `compliant`). `verify_pipeline.py` prints status with icons (✅ ➖ 🧮 ❌ ❓).

**Interview line:** *"My compliance check knows plug loads aren't NCC-regulated and
glazing needs a façade calc — and it lives behind an MCP tool, so swapping the seed
values for RAG over the live NCC touches the tool, not the agents."*

---

## 7. 🗂️ File map (🆕 / ✏️ changed this session)

```
retrofitgpt/
├── agents/
│   ├── retriever.py        Agent 1
│   ├── modeler.py          ✏️ now calls get_ncc_requirement for REAL compliance
│   ├── retrofit_catalog.py ✏️ led 6.0→4.5 W/m² (NCC-compliant); Watts_per_Floor_Area
│   ├── sim_runner.py       Agent 3 — FastMCPCaller + _unwrap live here
│   ├── analyzer.py         Agent 4
│   └── reviewer.py         Agent 5 (GL14 + LLM06)
├── mcp_server/tools/
│   ├── idf_tools.py        ✏️ modify_idf_component validates field in fieldnames
│   ├── results_tools.py    site-energy extraction
│   └── reference_tools.py  ✏️ get_ncc_requirement → real ncc_compliance check
├── verification/
│   ├── pydantic_schemas.py ✏️ RetrofitScenario.compliance_status added
│   ├── ashrae_checks.py    ✏️ data-aware GL14 thresholds (monthly 5/15, hourly 10/30)
│   ├── ncc_compliance.py   🆕 REAL NCC J7D3 table + check_ncc_compliance()
│   └── guardrails.py       OWASP LLM06
├── scripts/
│   ├── verify_pipeline.py  🆕 capstone E2E runner (+ --calibrate-demo)
│   ├── RUN_PIPELINE.md     🆕 how to run + expected outcomes
│   ├── verify_sim_runner.py / verify_retriever.py / verify_modeler.py
│   └── download_reference_data.py   (run first — Sydney EPW)
├── docs/
│   └── ARCHETYPE_AND_CALIBRATION.md 🆕 model decision + real tuning workflow + §6 FOR-WEBSITE
├── tests/                  93 tests (+ test_ncc_compliance.py 🆕, ashrae/modeler updated)
├── api/main.py             pipeline awaits all 5 real agents
├── .env                    keys + LLM_PROVIDER=anthropic (gitignored)
└── HANDOFF.md              full changelog history
```

---

## 8. ⚠️ KNOWN GAPS / honesty caveats (be precise in interviews)

| Gap | Where | Severity | Note |
|-----|-------|----------|------|
| Calibration uses **synthetic** bills (`--calibrate-demo`) | verify_pipeline | 🟡 | green path proof, NOT a real-building calibration; labelled everywhere. Real calibration needs a real building + tuning (workflow in the archetype doc) |
| NCC compliance is **Tier 1** (seed values) | ncc_compliance | 🟡 | values primary-verified, but only lighting is a numeric check; equipment=not-regulated, glazing=requires-calc. Tier 2 = RAG over live NCC |
| Glazing façade calculation not implemented | ncc_compliance | 🟡 | returns `requires_calculation` honestly |
| Catalog measures + costs are **SEED** | retrofit_catalog | 🟡 | replace with QS cost DB |
| `floor_area_m2` is the **511 fallback** (`estimated:true`) | retriever | 🟡 | compute from BuildingSurface or post-sim table |
| Tariff is a stub | reference | 🟡 | wire CDR Energy PRD API |
| Demo runs on the **DOE Small Office prototype**, not a real building | whole demo | 🟡 | reproducible archetype; see archetype doc; needs an "About the model" panel at deploy |

**None are bugs** — they're the seam where seed data ends and Phase 3 (RAG + real data)
begins.

---

## 9. 🚀 How to run / verify (on Taash's Mac mini)

```bash
cd "/Users/taashchikosi/Documents/Claude/Projects/Agentic AI Portfolio/retrofitgpt"

# once: Sydney EPW
python3 scripts/download_reference_data.py

# tests (no Docker) — expect 93 passed
pip install "pydantic>=2.0" pytest fastapi sse-starlette httpx pandas langgraph
python3 -m pytest

# ⭐ the capstone, GREEN demo path (Docker; EnergyPlus + Claude):
docker compose run --rm app python scripts/verify_pipeline.py --calibrate-demo

# the capstone with HONEST synthetic bills (Reviewer will likely withhold — correct):
docker compose run --rm app python scripts/verify_pipeline.py

# with a real bill (true calibration): --utility your_bills.json
```

Docker must use `docker compose` (pins linux/amd64; EnergyPlus is x86_64-only, runs
under emulation). First build ~50 min on a slow home network; rebuilds are cached.

---

## 10. 📍 NEXT — pick one (evidence-backed priorities)

Verified against a live EY AU AI-Architect posting + 2025–26 portfolio norms:

1. **✅ DONE (12 Jun 2026, this session) — Evals harness (Tier A) + NCC gap closed.**
   - `evals/run_evals.py` + `evals/test_cases/*.json` + `evals/README.md`: golden-case
     regression gate over the **deterministic** layer (invokes the REAL
     `analyse()`/`review()`/NCC checks over canned sim fixtures — no Docker/LLM needed).
     2 cases, 20 checks, exit-code gated, reports to `evals/results/`. **Mutation-tested**
     (proven to catch a savings collapse AND a reverted bug #7). Folded into pytest via
     `tests/test_evals.py`. **Suite now 102 green** (was 93: +5 NCC aggregate, +4 eval).
   - Negative control `uncalibrated_office_must_fail` proves the GL14 gate still
     **rejects** an uncalibrated model (regression guard for bug #6).
   - **NCC gap closed:** added the REAL J7D3(2)(a) **aggregate area-weighted** check
     `check_aggregate_lighting_compliance` — Σ(area×design) ≤ Σ(area×max IPD). The old
     per-space check was a simplification; the aggregate is what a certifier applies and
     can offset a single over-lit space. **Honest framing now: "Tier 1.5 — per-space +
     aggregate done; Table J7D3b/c adjustment factors + J4 fabric calc are Tier 2."**
   - All Table J7D3a seed values **primary-verified against the live ABCB NCC 2022 text**
     this session — every value matches (office ≥200 lx → 4.5, <200 lx → 2.5, etc.).
   - **✅ Tier B (`--live`) now BUILT too** — `evals/tier_b.py` gates the
     DeepSeek↔Claude swap by running the real LLM-judgement functions
     (`retriever._classify`, `modeler._select_measures`) against the configured
     provider. KEY INSIGHT: those are pure functions taking an injected `llm`, so
     Tier B feeds them CANNED IDF metadata + the real model — **no EnergyPlus, no
     Docker**; runs anywhere with a provider key. Checks: building_type ∈ allowed,
     select ⊆ catalog + must_include, **`llm_parsed`** (the model emitted valid JSON,
     not the silent agent fallback — catches a model that can't do strict-JSON), and
     **stability** across `--samples N` (flip-flop detector). Reports provider + model
     + token usage. Missing key / unreachable provider → clear message, never a fake
     regression. Proven in-sandbox with fake LLMs (`tests/test_evals_tierB.py`) + a
     stubbed-provider live-plumbing run. **Suite now 108 green.**
   - **To gate a swap (on Taash's Mac):** `LLM_PROVIDER=anthropic python3
     evals/run_evals.py --live` then `LLM_PROVIDER=deepseek … --live`; both must stay
     green. Compare the token usage each prints.
   - **✅ Multi-archetype + citation gate added (same session):** golden cases now
     cover `medium_office` (Melbourne z6), `retail` (Brisbane z2, NCC retail 14 W/m²),
     `school` (Canberra z7, learning-area 4.5 W/m²) on top of the DOE small office —
     **Tier A = 5 cases / 71 checks.** Bands computed from the real analyzer output.
     Tier B gained a **citation-judgement** check: `verification.guardrails.
     judge_claims_grounded` (LLM06 nuance the number-matcher can't catch) — a clean
     business case must read `supported`, a version with a fabricated rebate/grant/
     guarantee must read `unsupported`, fail-closed on bad JSON. Wired as the
     `verification`-task LLM in `--live` (Reviewer-class). **Suite now 115 green.**
     NOTE: `judge_claims_grounded` is available for the Reviewer to adopt as an
     optional LLM second-opinion, but the default Reviewer path stays deterministic
     (unchanged) — so nothing in production behaviour shifted.
   - **STILL TODO (lower priority):** classify expectations for retail/school lean on
     metadata *hints* in `idf_meta` (the real Retriever classify input is thin —
     zone_count/floor/hvac/constructions/location only). A genuinely robust classifier
     would inspect Zone names / People objects; that's a Retriever improvement, not an
     eval one.

   - **🔑 LIVE SWAP DECISION (gated 12 Jun 2026, real providers, 3 samples/case):**
     | Node (router task) | Claude (sonnet-4-6) | DeepSeek (deepseek-chat) | Verdict |
     |---|---|---|---|
     | Retriever classify (`retrieval`) | 4/4 ✅ | **fails** — stably mis-sizes the 511 m² office as medium; after a prompt fix it then destabilised retail + mislabelled the school | **keep on Claude** |
     | Modeler select (`modelling`) | ✅ | ✅ | DeepSeek OK |
     | Citation judge (`verification`) | ✅ caught all fabricated rebates/grants | ✅ caught them too | DeepSeek OK |

     Cost (full Tier-B run): Claude **8335/2302** tok · DeepSeek **7440/1592** tok.
     **Conclusion:** the router's cost-tiered default is sound, BUT classification is
     DeepSeek's weak node — two prompt iterations fixed the target case yet broke
     others on DeepSeek (Claude stayed 4/4 throughout). So: **route `retrieval` to
     Claude; `modelling` + the citation gate can use DeepSeek.** Kept the explicit
     office-size-threshold prompt (`agents/retriever.py::_CLASSIFY_SYSTEM`) — it's more
     correct and Claude-safe; guard test in `tests/test_retriever.py`. The lesson:
     *prompt-engineering around a weaker model on a low-stakes node is whack-a-mole;
     let the eval pick the model.* **Suite 116 green.**
2. **⭐ Live deployment.** Ship the capstone on the ONE unified portfolio site (see
   `Portfolio_Demo_Site_Plan.md` / `portfolio-one-website` memory). A clickable demo
   beats any internal feature. **MUST include an "About the model" panel + a "Demo
   calibration" badge** (see `docs/ARCHETYPE_AND_CALIBRATION.md` §6).

   **DEPLOY-READINESS (assessed 12 Jun 2026; VPS is up):**
   - ✅ Backend core: Dockerfile (amd64/EnergyPlus, first build ~50 min), real
     `/health` w/ readiness checks, per-IP rate-limit, real 5-agent SSE pipeline.
   - ✅ **Eval-gated routing** wired into the deploy default: `retrieval`→Claude,
     `verification`→Claude, `modelling`→DeepSeek (`router/model_router.py`).
   - ✅ **Hard token/cost cap** — rolling 24h global budget in `model_router.complete()`
     (`LLM_MAX_TOKENS_PER_DAY`, default 500k; raises `TokenBudgetExceeded` BEFORE spend);
     `/api/runs` returns 503 when spent; `/health` reports budget. Guards the wallet,
     now that every run hits Claude twice + DeepSeek.
   - ✅ **CORS locked** — env `ALLOWED_ORIGINS` allowlist (no more `*`); methods
     restricted. Tests: `tests/test_deploy_guards.py`. **Suite now 125 green.**
   - ✅ **Case-study page + About panel BUILT** — `frontend/app/retrofitgpt/page.tsx`:
     hero + live `/health` status dot (env `NEXT_PUBLIC_API_BASE`, default :8001),
     problem, 5-agent architecture, real eval metrics (125 tests / 5 cases / GL14 /
     NCC), ADR (the swap decision + green-but-wrong bugs), and the §6 **"About the
     model" panel + "Demo calibration" badge** (exact honesty copy, EUI labelled
     kWh/m²·yr). Uses only installed deps (Tailwind tokens + lucide-react); matches the
     design system. NOT type-checked live (no node_modules in sandbox) — `npm run dev`
     then visit `/retrofitgpt` to confirm it renders.
   - ✅ **One-click auto-run BUILT.** Backend: `RunIn.demo_calibrate` + disclosed
     baseline-derived bills in `_drive_pipeline`, full business case stored +
     `GET /api/runs/{id}/result`, richer reviewer `done` payload (tests:
     `tests/test_auto_run.py`). Frontend `frontend/app/page.tsx`: one prominent **Run**
     button → POST run (demo_calibrate) → live SSE 5-agent trace → **auto-approves the
     HITL gate** → renders the business case (savings/payback/NPV/tCO₂e) + Reviewer
     verdict + the **Demo-calibration badge** (links to `/retrofitgpt#about-model`).
     Deliberately one-click, NOT auto-on-mount (auto-run would let crawlers drain the
     token budget). **Suite now 131 green.** Frontend NOT rendered-tested in sandbox —
     `npm run dev`, click Run, confirm the trace streams + result renders.
   - 🟧 **Remaining before public launch:** **platform integration** — this UI lives in
     RetrofitGPT's own `frontend/`; per the locked one-site decision it should become a
     route in the unified Vercel platform (or this app is deployed + iframed). Decide at
     platform-build time. Set `NEXT_PUBLIC_API_BASE` (frontend) ↔ `ALLOWED_ORIGINS`
     (backend) to match, and actually `docker compose up` the container on the VPS.
   - 🟧 **VPS env to set:** `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, **leave
     `LLM_PROVIDER` UNSET** (so the cost-tiered eval-gated default applies — NOT
     `=anthropic`, which is dev-only), `ALLOWED_ORIGINS=https://<your-vercel-domain>`,
     optional `LLM_MAX_TOKENS_PER_DAY` / `RATE_LIMIT_PER_MIN`.
3. **Tier 2 NCC RAG.** NCC Section J + NABERS into pgvector; `get_ncc_requirement`
   retrieves real clauses + citations. Natural Phase-3 brick; makes §6 fully real.
4. **🎓 Learning session.** Teach the 5-agent system, the MCP boundary, the
   deterministic-vs-LLM split, and the common thread of all 7 green-but-wrong bugs.
5. **💼 LinkedIn post.** "Built a real 5-agent MCP pipeline driving EnergyPlus with a
   GL14 + OWASP-LLM06 + real NCC Section J governance layer — and caught 7 green-but-
   wrong bugs with domain knowledge."

---

## 11. 🧠 How to work with Taash (she set these rules — follow them)

- 🎨 **Visual / systems thinker** — diagrams, tables, structured layouts, emojis. Full
  picture first, then steps. **No walls of text.** Bullets over paragraphs.
- 🗣️ **Advisor, not a yes-man.** Never open with agreement. Lead with the uncomfortable
  truth. Tag confidence `[Certain]/[Likely]/[Guessing]`. Disagree with structure
  (reason → alternative → risk). Don't fold under pushback unless given new information.
- 🔬 **Verify, don't assume.** Primary sources, run the code, show the proof. **All 7
  bugs passed a green check — always sanity-check the numbers against domain knowledge.**
- 📣 **Narrate before each step** — one line on *what* + *why*.
- 🎓 **Cadence:** build milestone → 🎓 visual learning session → 💼 LinkedIn post.
- 💻 **Terminal reality:** she runs commands on her Mac mini; remind her to `cd` into
  the project. Docker = `docker compose`. Home network is slow.
- 🚫 The assistant **cannot** run EnergyPlus / eppy / live-LLM in its sandbox — build
  with injected fakes, hand Taash a `verify_*.py` (or the capstone) for the real proof.
```
