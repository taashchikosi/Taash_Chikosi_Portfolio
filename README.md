# ⚡ RetrofitGPT
### Autonomous Building Retrofit & Decarbonisation Advisor 🇦🇺

<!-- Replace OWNER with your GitHub username/org once the repo is pushed. -->
[![tests](https://github.com/OWNER/retrofitgpt/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/retrofitgpt/actions/workflows/ci.yml)

> 🚧 **Phase 1 in progress** — MCP server foundation. Full story-driven README lands at v1 (see project plan §16).

Multi-agent AI system: upload a building energy model + 12 months of bills → physics-verified retrofit business case (savings %, payback, tCO₂e) built on Australian data (NABERS · NCC Section J · CDR tariffs · NGA carbon factors).

**Stack:** LangGraph · FastMCP · EnergyPlus · Pydantic v2 · pgvector · Langfuse · DeepEval · Next.js + assistant-ui

## Quick start
```bash
cp .env.example .env   # fill in keys
docker compose up -d
```

## Repo layout
See `RetrofitGPT_Project_Plan.md` §11 (project folder) for the full map.
