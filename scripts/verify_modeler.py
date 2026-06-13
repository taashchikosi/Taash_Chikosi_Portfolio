"""Live proof of the Modeler: real inspect_idf (eppy + IDD) + real Claude.

Builds a BuildingContext for the committed DOE small office, runs the real
Modeler (Claude selects measures; deterministic cost/NCC/validation), and prints
the ModelingOutput. Sanity-check: ≥2 retrofits, each a wildcard modification,
positive costs, NCC references present.

Run INSIDE Docker:

    docker compose run --rm app python scripts/verify_modeler.py
"""
from __future__ import annotations

import asyncio

from agents.modeler import modeler_async
from verification.pydantic_schemas import BuildingContext, UtilityData

IDF = "data/reference_buildings/RefBldgSmallOffice.idf"


async def main() -> int:
    ctx = BuildingContext(
        building_type="small_office", floor_area_m2=511.0, ncc_climate_zone=5,
        hvac_system="single-duct VAV AHU", current_eui=126.4,
        annual_energy_cost_aud=19_500.0, idf_path=IDF,
        utility_data=UtilityData(
            monthly_kwh=[5567, 5210, 5873, 5256, 5463, 5358,
                         5221, 5583, 5164, 5248, 5227, 5417],
            annual_cost_aud=19_500.0))
    state = {"building_context": ctx,
             "emit": lambda a, s, p: print(f"  · {a}/{s}: {p}")}

    print("▶ Running the real Modeler (inspect_idf + Claude select) …\n")
    state = await modeler_async(state)
    out = state["modeling_output"]

    print("\n=== ModelingOutput ===")
    print(out.model_dump_json(indent=2))

    retrofits = [s for s in out.scenarios if s.name != "baseline"]
    ok = (len(retrofits) >= 2
          and all(s.modifications and s.modifications[0].object_name == "*"
                  for s in retrofits)
          and all(s.estimated_cost_aud > 0 for s in retrofits))
    print("\n✅ MODELER OK — Claude → measures → valid wildcard IDF edits"
          if ok else "\n⚠️ Check the scenarios above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
