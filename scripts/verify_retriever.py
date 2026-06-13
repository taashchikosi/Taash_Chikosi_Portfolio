"""Live proof of the Retriever: real inspect_idf (eppy + IDD) + real Claude.

Runs the actual agent against the committed DOE small-office IDF, with the LLM
routed through model_router (LLM_PROVIDER in .env decides Claude vs DeepSeek).
Prints the BuildingContext so you can sanity-check floor area, EUI, climate zone.

Run INSIDE Docker (eppy needs the EnergyPlus IDD):

    docker compose run --rm app python scripts/verify_retriever.py

Needs ANTHROPIC_API_KEY (or DEEPSEEK_API_KEY) in .env. EUI sanity: a small
office should land ~100–200 kWh/m²/yr.
"""
from __future__ import annotations

import asyncio

from agents.retriever import retriever_async

IDF = "data/reference_buildings/RefBldgSmallOffice.idf"


async def main() -> int:
    # A plausible 12-month bill for the demo building (replace with a real one).
    state = {
        "idf_path": IDF,
        "epw_path": "data/reference_buildings/weather/AUS_NSW_Sydney.epw",
        "raw_utility": {
            "monthly_kwh": [5567, 5210, 5873, 5256, 5463, 5358,
                            5221, 5583, 5164, 5248, 5227, 5417],
            "annual_cost_aud": 19_500.0,
            "tariff_type": "single rate",
        },
        "emit": lambda a, s, p: print(f"  · {a}/{s}: {p}"),
    }

    print("▶ Running the real Retriever (inspect_idf + Claude classify) …\n")
    state = await retriever_async(state)
    ctx = state["building_context"]

    print("\n=== BuildingContext ===")
    print(ctx.model_dump_json(indent=2))

    eui_ok = 50 < ctx.current_eui < 400
    zone_ok = 1 <= ctx.ncc_climate_zone <= 8
    print("\n✅ RETRIEVER OK" if (eui_ok and zone_ok) else
          "\n⚠️ Check the values above (EUI or climate zone looks off).")
    return 0 if (eui_ok and zone_ok) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
