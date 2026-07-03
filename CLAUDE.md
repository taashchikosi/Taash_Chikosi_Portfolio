# CLAUDE.md — RetrofitGPT / Agentic Energy Modeller

Autonomous multi-agent system that drives real EnergyPlus simulations behind an
MCP tool layer and governs its own outputs. **Hard rule: the LLM never authors a
number** — every figure comes from the simulation or deterministic math.

## 👉 Active task (read this first)

**`docs/CLAUDE_CODE_TASK_MultiCity.md`** — finish the multi-city scope (Medium +
Large Office × Perth/Sydney/Melbourne/Brisbane). Code is done + tested; the
remaining steps need local internet + the CBD register (download EPWs/IDF, build
per-city cohorts, paste verified medians, run tests). Do those, don't redo the code.

## Orientation

- **Read order:** `HANDOFF_NEXT_SESSION.md` → `docs/ARCHETYPE_AND_CALIBRATION.md`
  → `HANDOFF.md` → `RetrofitGPT_Project_Plan.md`.
- **Single source of truth** for buildings/cities: `data/reference_buildings/catalog.json`
  (backend) ↔ `frontend/lib/energy-modeller-catalog.ts` (UI). Keep them in sync.
- **Scope is offices-only** by design — see `docs/ARCHETYPE_AND_CALIBRATION.md` §1.5
  before adding any building type.

## Verify before commit

```bash
python -m pytest tests/ -q          # backend (currently 142 green)
cd frontend && npx tsc --noEmit     # frontend types
```

Remote: `github.com/taashchikosi/Taash_Chikosi_Portfolio`. The working tree has
pre-existing untracked frontend files — stage deliberately, never `git add -A` blind.
