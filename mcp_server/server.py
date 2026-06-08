"""⚡ RetrofitGPT — EnergyPlus FastMCP Server (Phase 1 skeleton).

Run locally:
    python -m mcp_server.server

v1 ships 20 core tools (see RetrofitGPT_Project_Plan.md §4).
Phase 1 implements the first 5 IDF tools + health check; the rest land
as stubs and are filled in across Phases 1–3.
"""
import os
import subprocess

from fastmcp import FastMCP

from mcp_server.tools.idf_tools import register_idf_tools

mcp = FastMCP("EnergyPlus Retrofit Server")


@mcp.resource("health://status")
def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "energyplus_version": _energyplus_version(),
    }


def _energyplus_version() -> str:
    """Return the installed EnergyPlus version, or 'not installed'."""
    try:
        out = subprocess.run(
            ["energyplus", "--version"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or out.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "not installed"


# ── Register tool groups ────────────────────────────────────────────
register_idf_tools(mcp)
# Phase 1 (next): register_simulation_tools(mcp), register_results_tools(mcp)
# Phase 1 (next): register_reference_tools(mcp)
# Phase 3:        register_analysis_tools(mcp), register_tariff_tools(mcp)


if __name__ == "__main__":
    # NOTE: bearer-token auth (MCP_API_KEY) is enforced when served over HTTP
    # via FastAPI in api/main.py. stdio mode (below) is for local dev.
    mcp.run()
