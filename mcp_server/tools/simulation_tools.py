"""Simulation Control tools (2 of the 20 core tools).

run_simulation · get_simulation_status

EnergyPlus runs as a subprocess (CLI) in a background thread per job —
simple, robust, parallel-safe. Job registry is in-memory (Phase 1);
swap to Postgres if persistence across restarts is needed.
"""
import subprocess
import threading
import time
import uuid
from pathlib import Path

from mcp_server.schemas.tool_schemas import wrap

OUTPUT_ROOT = Path("data/sim_output")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

_JOBS: dict[str, dict] = {}  # job_id -> {status, idf, epw, out_dir, runtime, error}
MAX_RETRIES = 3


def _run_energyplus(job_id: str) -> None:
    job = _JOBS[job_id]
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                [
                    "energyplus",
                    "--weather", job["epw"],
                    "--output-directory", str(out_dir),
                    "--readvars",          # produce eplusout.csv
                    "--annual",
                    job["idf"],
                ],
                capture_output=True, text=True, timeout=1800,
            )
            job["runtime"] = round(time.time() - start, 1)
            if result.returncode == 0:
                job["status"] = "success"
                return
            job["error"] = (result.stderr or result.stdout)[-2000:]
            job["status"] = "failed" if attempt == MAX_RETRIES else "retrying"
        except subprocess.TimeoutExpired:
            job["status"] = "timeout"
            job["error"] = "EnergyPlus exceeded 30 min"
            return
        except FileNotFoundError:
            job["status"] = "failed"
            job["error"] = "energyplus binary not found — run inside Docker"
            return


def register_simulation_tools(mcp) -> None:
    @mcp.tool()
    def run_simulation(idf_path: str, epw_path: str, scenario_name: str = "run") -> dict:
        """Start an async EnergyPlus simulation. Returns a job_id to poll."""
        for p, label in [(idf_path, "IDF"), (epw_path, "EPW")]:
            if not Path(p).exists():
                return wrap("run_simulation", {"error": f"{label} not found: {p}"})
        job_id = f"{scenario_name}-{uuid.uuid4().hex[:8]}"
        _JOBS[job_id] = {
            "status": "running", "idf": idf_path, "epw": epw_path,
            "out_dir": str(OUTPUT_ROOT / job_id), "runtime": None, "error": None,
        }
        threading.Thread(target=_run_energyplus, args=(job_id,), daemon=True).start()
        return wrap("run_simulation", {"job_id": job_id, "status": "running"})

    @mcp.tool()
    def get_simulation_status(job_id: str) -> dict:
        """Poll a simulation job: running | success | failed | timeout."""
        job = _JOBS.get(job_id)
        if job is None:
            return wrap("get_simulation_status", {"error": f"unknown job_id: {job_id}"})
        return wrap("get_simulation_status", {
            "job_id": job_id,
            "status": job["status"],
            "runtime_seconds": job["runtime"],
            "output_dir": job["out_dir"],
            "error": job["error"],
        })
