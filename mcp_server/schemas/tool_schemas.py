"""Pydantic schemas for all MCP tool inputs/outputs.

Every tool response is wrapped in ToolResponse (schema-versioned) so agents
can detect breaking changes — a deliberate governance signal.
"""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"


class ToolResponse(BaseModel):
    """Envelope for every MCP tool response."""

    schema_version: str = SCHEMA_VERSION
    tool_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any]


class IDFSummary(BaseModel):
    """Output of load_idf / inspect_idf."""

    idf_path: str
    energyplus_version: str | None = None
    building_name: str | None = None
    building_type: str | None = None
    floor_area_m2: float | None = None
    zone_count: int = 0
    zones: list[str] = []
    hvac_systems: list[str] = []
    construction_count: int = 0


class UtilityData(BaseModel):
    """12 months of utility bills — required for ASHRAE GL14 calibration."""

    monthly_kwh: list[float] = Field(..., min_length=12, max_length=12)
    annual_cost_aud: float
    tariff_type: str = "single rate"

    @property
    def annual_kwh(self) -> float:
        return sum(self.monthly_kwh)


def wrap(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Convenience: build a schema-versioned ToolResponse dict."""
    return ToolResponse(tool_name=tool_name, data=data).model_dump(mode="json")
