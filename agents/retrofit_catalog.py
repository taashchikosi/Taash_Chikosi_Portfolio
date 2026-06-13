"""Seed catalog of retrofit measures (Phase 2).

Each measure maps to a building-wide EnergyPlus modification (object_name='*')
plus an indicative cost. These are SEED values for the demo — costs and target
values are marked VERIFY and must be replaced with a QS cost database + per-model
tuning before any client use. The portfolio value is the agent architecture
(LLM selects → deterministic cost/NCC/validation → valid IDF edits → sim), not
the precision of these seed numbers.

Cost model: estimated_cost_aud = cost_base_aud + cost_per_m2_aud × floor_area_m2.
"""
from __future__ import annotations

from dataclasses import dataclass

from verification.pydantic_schemas import IDFModification


@dataclass(frozen=True)
class Measure:
    key: str
    name: str
    description: str
    object_type: str        # EnergyPlus object the change applies to
    field_name: str         # eppy field name
    new_value: str          # target value (absolute) — VERIFY per model
    ncc_component: str       # key for get_ncc_requirement
    cost_base_aud: float
    cost_per_m2_aud: float

    def modification(self) -> IDFModification:
        """Building-wide IDFModification (applies to every object of the type)."""
        return IDFModification(
            object_type=self.object_type, object_name="*",
            field=self.field_name, new_value=self.new_value)

    def estimate_cost(self, floor_area_m2: float) -> float:
        return round(self.cost_base_aud + self.cost_per_m2_aud * float(floor_area_m2), 0)


# key → Measure. Targets are simple field changes so they apply cleanly via the
# wildcard modify_idf_component. (VERIFY all values.)
CATALOG: dict[str, Measure] = {
    "led_lighting": Measure(
        key="led_lighting", name="LED lighting upgrade",
        description="Re-lamp all luminaires to LED; lighting power density → 4.5 W/m² "
                    "(NCC 2022 J7D3 office maximum).",
        object_type="Lights", field_name="Watts_per_Floor_Area",
        new_value="4.5", ncc_component="lighting_power_density",
        cost_base_aud=2_000.0, cost_per_m2_aud=25.0),
    "efficient_equipment": Measure(
        key="efficient_equipment", name="Efficient plug loads",
        description="High-efficiency office equipment; equipment power density → ~8 W/m².",
        object_type="ElectricEquipment", field_name="Watts_per_Floor_Area",
        new_value="8.0", ncc_component="equipment_power_density",
        cost_base_aud=1_500.0, cost_per_m2_aud=15.0),
    "double_glazing": Measure(
        key="double_glazing", name="Double glazing",
        description="Upgrade windows to double glazing (U ≈ 1.8 W/m²K).",
        object_type="WindowMaterial:SimpleGlazingSystem", field_name="UFactor",
        new_value="1.8", ncc_component="glazing_u_value",
        cost_base_aud=5_000.0, cost_per_m2_aud=60.0),
}


def measure_keys() -> list[str]:
    return list(CATALOG)
