"""Live proof that the physics loop is closed.

Drives ONE real EnergyPlus baseline simulation through the Sim Runner's actual
MCP orchestration — the in-memory FastMCP client calling clone_idf →
run_simulation → get_simulation_status → results tools — against the committed
DOE small-office model and the Sydney weather file.

This is the on-machine companion to tests/test_sim_runner.py (which fakes the
client). Here nothing is faked: real MCP protocol, real EnergyPlus subprocess.

Run INSIDE Docker (EnergyPlus only exists there):

    docker compose run --rm app python scripts/verify_sim_runner.py

Prereqs: scripts/download_reference_data.py has fetched the Sydney EPW.
Exit code 0 = physics loop closed; 1 = sim did not produce a usable result.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from agents.sim_runner import FastMCPCaller, _simulate
from verification.pydantic_schemas import RetrofitScenario

IDF = "data/reference_buildings/RefBldgSmallOffice.idf"
EPW = "data/reference_buildings/weather/AUS_NSW_Sydney.epw"
FLOOR_AREA_M2 = 511.0  # DOE small office


async def main() -> int:
    for p, label in [(IDF, "IDF"), (EPW, "EPW")]:
        if not Path(p).exists():
            print(f"❌ {label} not found: {p}\n   "
                  f"Run: python3 scripts/download_reference_data.py")
            return 1

    baseline = RetrofitScenario(
        name="baseline", description="as-built", modifications=[],
        estimated_cost_aud=0, code_compliance=True, ncc_reference="—")

    def emit(agent, status, payload):
        print(f"  · {agent}/{status}: {payload}")

    print("▶ Driving one real EnergyPlus baseline sim over the MCP client …\n")
    async with FastMCPCaller() as call:
        result = await _simulate(call, IDF, EPW, baseline, FLOOR_AREA_M2, emit)

    print("\n=== SimulationResult ===")
    print(result.model_dump_json(indent=2))

    ok = result.simulation_status == "success"
    print("\n✅ PHYSICS LOOP CLOSED — agent → MCP → EnergyPlus → results"
          if ok else
          "\n❌ Sim did not produce a usable result. Common cause: the IDF lacks\n"
          "   `Output:Meter,Electricity:Facility,Monthly;` — add it, then re-run.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
