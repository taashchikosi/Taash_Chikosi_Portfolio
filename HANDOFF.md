# 🤝 RetrofitGPT — Session Handoff

> **Purpose:** single source of truth for picking this project up in a new chat.
> Read this first, then `PROJECT_MEMORY.md` (decisions + user context) and
> `RetrofitGPT_Project_Plan.md` (technical reference).
>
> **Last updated:** 10 June 2026 · **Build state:** Phase 1 ✅ done · Phase 2 ~90%

---

## 🎯 30-Second Summary

RetrofitGPT is an autonomous multi-agent system: upload a building energy model
(`.idf`) + 12 months of bills → it runs EnergyPlus retrofit simulations → outputs
an audit-ready decarbonisation business case (savings %, payback, tCO₂e, NPV),
verified against ASHRAE Guideline 14 calibration and an OWASP LLM06 guardrail.

- **Who:** Taash (Taashira Chikosi) — building-energy engineer (IESVE background), in school
- **Goal:** get hired in 🇦🇺 **Australia** (Big 4 sustainability / energy companies) while still studying
- **Market:** all data is Australian (NABERS, NCC Section J, CDR tariffs, NGA carbon factors, AUD)
- **Why it wins:** physics-in-the-loop + governance + cost discipline = senior-level hiring signal

---

## ✅ What's BUILT and TESTED

| Layer | Status | Notes |
|-------|--------|-------|
| Repo scaffold + Docker + devcontainer | ✅ | `docker-compose.yml`, `Dockerfile` (installs EnergyPlus 24.2) |
| **20/20 MCP tools** (FastMCP) | ✅ | IDF (5), simulation (2), results (5), reference (4), analysis (4) |
| Pydantic schemas (all agent IO) | ✅ | `verification/pydantic_schemas.py` |
| ASHRAE GL14 calibration (NMBE, CV-RMSE) | ✅ **tested** | passes 3%-off model, fails 50%-off |
| OWASP LLM06 guardrail | ✅ **tested** | catches fabricated numbers; fixed a real number-parser bug |
| Model router (DeepSeek + Claude) | ✅ | `router/model_router.py` — both keys wired |
| LangGraph supervisor + routing | ✅ | `agents/supervisor.py` (calibration→Modeler, claim→Analyzer) |
| **Real Analyzer agent** | ✅ **tested** | savings/payback/NPV/carbon match hand-calcs exactly |
| **Real Reviewer agent** | ✅ **tested** | deterministic gate, approves valid run |
| FastAPI backend (REST + SSE + HITL) | ✅ | `api/main.py` — full stub pipeline runs end-to-end |
| Next.js + assistant-ui frontend | ✅ scaffold | `frontend/` — Analysis + Dashboard pages, enterprise theme |
| Demo buildings (DOE small + medium office) | ✅ downloaded | in `data/reference_buildings/` |

**Agents 1–4 currently run as stubs** (`agents/stubs.py`) so the pipeline works
end-to-end today. Analyzer + Reviewer are already the REAL implementations.

---

## 🚧 What's NOT done yet (next session picks up here)

1. **Real Retriever agent** (`agents/retriever.py`) — parse IDF via MCP `inspect_idf`,
   query RAG, emit `BuildingContext`. *Needs live DeepSeek to test.*
2. **Real Modeler agent** (`agents/modeler.py`) — propose retrofit scenarios + params,
   validate against NCC. *Needs live DeepSeek.*
3. **Real Sim Runner** — replace stub with actual EnergyPlus MCP calls. *Needs Docker up.*
4. **RAG layer** (Phase 3) — ingest NCC Section J + NABERS into pgvector (free docs,
   user downloads them; `data/codes/` is gitignored).
5. **CDR tariff tool** — wire the public Australian tariff API (currently a stub).
6. **Frontend ↔ backend live wiring** — connect SSE stream to the agent-trace panel.
7. **Eval harness** (Phase 3) — 20+ DeepEval cases, GitHub Actions CI badge.
8. **Deploy** (Phase 4) — Vercel (frontend) + HuggingFace Spaces (backend), Loom video.

---

## 🔑 Credentials (all saved in `.env`, which is gitignored)

| Key | Status |
|-----|--------|
| `DEEPSEEK_API_KEY` | ✅ saved |
| `ANTHROPIC_API_KEY` | ✅ saved |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | ✅ saved (Tokyo region: `jp.cloud.langfuse.com`) |

> ⚠️ Keys were pasted in chat — fine for now, rotate if ever exposed publicly.

---

## ⚠️ Known issues / gotchas

- **🌦️ Sydney weather file not yet downloaded.** onebuilding.org renamed their files.
  The download script now **auto-discovers** the current Sydney URL from the directory
  index. User needs to re-run `python3 scripts/download_reference_data.py`.
  Fallback: manually grab any `Sydney…TMYx….zip` from
  `https://climate.onebuilding.org/WMO_Region_5_Southwest_Pacific/AUS_Australia/NSW_New_South_Wales/`,
  unzip, place the `.epw` at `data/reference_buildings/weather/AUS_NSW_Sydney.epw`.
- **🐍 User's host Python is 3.9.** Any script run on the host (not Docker) must use
  `from __future__ import annotations` for `X | None` syntax. Docker uses 3.11.
- **📊 NGA carbon factors are PLACEHOLDER.** `data/factors/nga_factors_2025.json` values
  MUST be verified against the official DCCEEW NGA workbook before any demo.
- **📜 NCC lookups are seed data.** Real NCC values arrive with the RAG layer (Phase 3);
  current `get_ncc_requirement` has a tiny seed dict marked "VERIFY".
- **🔁 git in this environment** sometimes leaves a `.git/HEAD.lock` — if a commit fails,
  `rm -f .git/HEAD.lock` then retry.
- **EnergyPlus can't run in the assistant's sandbox** — only on the user's machine via
  Docker. The agent cannot test real simulations; it tests the deterministic layers.

---

## 🚀 How to run it (on Taash's machine)

```bash
cd "/Users/taashchikosi/Documents/Claude/Projects/Agentic AI Portfolio/retrofitgpt"

# 1) get demo data (buildings already present; this grabs Sydney weather)
python3 scripts/download_reference_data.py

# 2) boot backend (first build ~10-15 min — installs EnergyPlus)
docker compose up -d --build

# 3) pre-cache baseline sims (instant-demo mode)
docker compose run --rm app python scripts/precache_baselines.py

# 4) frontend
cd frontend && npm install && npm run dev
# → http://localhost:3000   (backend: http://localhost:8080/docs)
```

---

## 🗂️ Where things live

```
retrofitgpt/
├── mcp_server/tools/     20 MCP tools (idf, simulation, results, reference, analysis)
├── agents/               supervisor + reviewer/analyzer (real) + stubs (1-4)
├── verification/         pydantic schemas, ashrae_checks, guardrails  ← all tested
├── router/               model_router.py (DeepSeek + Claude)
├── api/main.py           FastAPI REST + SSE + HITL
├── frontend/             Next.js + assistant-ui (Analysis + Dashboard)
├── data/                 reference_buildings/, factors/ (NGA), codes/ (gitignored)
├── scripts/              download_reference_data.py, precache_baselines.py
├── PROJECT_MEMORY.md     decisions + user context (READ 2nd)
├── RetrofitGPT_Project_Plan.md   full technical spec (READ 3rd)
└── HANDOFF.md            ← you are here
```
*(`PROJECT_MEMORY.md` and `RetrofitGPT_Project_Plan.md` live one level up, in the
portfolio folder, alongside the PDFs.)*

---

## 🧠 How to work with Taash (critical — see PROJECT_MEMORY.md §"HOW TAASH LEARNS")

- 🎨 Visual learner — diagrams, tables, structured layouts, emojis. **No walls of text.**
- 🧩 Systems thinker — give the full picture first, then steps.
- 🔬 Explain with **everyday analogies + concrete numbers** when she's stuck.
- 🗣️ She wants an **advisor, not a yes-man** — challenge assumptions, tag confidence
  `[Certain]/[Likely]/[Guessing]`, lead with the uncomfortable truth.
- 📣 **Narrate before each step** — one line on *what* + *why* before doing it.
- 🎓 Before each LinkedIn post: run a **visual learning session** first.
  Sequence: **Build milestone → 🎓 learning session → 💼 LinkedIn post.**

---

## 📍 Recommended next action for the new session

> "Docker is installed and keys are in. Re-run the weather download, then
> `docker compose up -d --build`. Once the backend is live, build the real
> Retriever + Modeler agents and test them against live DeepSeek — that closes
> Phase 2. Then move to RAG (Phase 3)."

Confirm with Taash where she is before assuming — she may have already booted Docker.
