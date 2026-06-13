"""Sim Runner orchestration tests — fake MCP client, no EnergyPlus / Docker.

These prove the *agent's* logic (clone → modify → run → poll → extract →
assemble) independent of EnergyPlus. The live physics is verified separately on
the user's machine via Docker (see HANDOFF verification recipe).
"""
from __future__ import annotations

from types import SimpleNamespace

from agents.sim_runner import _unwrap, sim_runner
from verification.pydantic_schemas import (
    AnalyzerOutput, IDFModification, ModelingOutput, RetrofitScenario,
    SimRunnerOutput, SimulationResult,
)


# ── Fake MCP tool caller ───────────────────────────────────────────────────
class FakeCaller:
    """Async callable that mimics the 9 EnergyPlus MCP tools with canned data.

    `statuses` is the sequence get_simulation_status returns on successive polls
    (so we can simulate running→running→success or an outright failure).
    `fail_tool` forces an {"error": ...} return for one tool name.
    """

    def __init__(self, *, statuses=None, monthly=None, fail_tool=None,
                 annual_total=50_000.0, eui=97.8):
        self.calls: list[tuple[str, dict]] = []
        self._statuses = statuses or ["success"]
        self._poll_idx = 0
        self._monthly = monthly if monthly is not None else [1_000.0] * 12
        self._fail_tool = fail_tool
        self._annual = annual_total
        self._eui = eui

    def count(self, name: str) -> int:
        return sum(1 for n, _ in self.calls if n == name)

    async def __call__(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        if name == self._fail_tool:
            return {"error": f"forced failure in {name}"}
        if name == "clone_idf":
            return {"cloned_path": f"/work/{kwargs['scenario_name']}.idf",
                    "scenario": kwargs["scenario_name"]}
        if name == "modify_idf_component":
            return {"object_name": kwargs["object_name"],
                    "field": kwargs["field"], "new_value": kwargs["new_value"]}
        if name == "run_simulation":
            return {"job_id": f"{kwargs['scenario_name']}-deadbeef", "status": "running"}
        if name == "get_simulation_status":
            st = self._statuses[min(self._poll_idx, len(self._statuses) - 1)]
            self._poll_idx += 1
            return {"job_id": kwargs["job_id"], "status": st,
                    "runtime_seconds": 12.3, "output_dir": "/out/run", "error": None}
        if name == "get_annual_energy":
            return {"annual_kwh_by_fuel": {"Electricity": self._annual},
                    "total_kwh": self._annual}
        if name == "get_monthly_energy":
            return {"monthly_kwh": list(self._monthly)}
        if name == "get_eui":
            return {"eui_kwh_m2": self._eui, "total_kwh": self._annual,
                    "floor_area_m2": kwargs["floor_area_m2"]}
        if name == "get_energy_end_uses":
            return {"end_uses_kwh": {"Heating": 12_000.0, "Cooling": 8_000.0}}
        return {}


# ── Fixtures ───────────────────────────────────────────────────────────────
def _baseline() -> RetrofitScenario:
    return RetrofitScenario(name="baseline", description="as-built",
                            modifications=[], estimated_cost_aud=0,
                            code_compliance=True, ncc_reference="—")


def _heat_pump() -> RetrofitScenario:
    return RetrofitScenario(
        name="heat_pump", description="ASHP",
        modifications=[IDFModification(
            object_type="Coil:Heating:Fuel", object_name="Main Heat",
            field="Nominal_Efficiency", new_value="3.5")],
        estimated_cost_aud=42_000, code_compliance=True,
        ncc_reference="NCC 2022 J6D")


def _glazing() -> RetrofitScenario:
    return RetrofitScenario(
        name="glazing", description="double glazing",
        modifications=[IDFModification(
            object_type="WindowMaterial:SimpleGlazingSystem",
            object_name="Win", field="UFactor", new_value="1.8")],
        estimated_cost_aud=28_000, code_compliance=True,
        ncc_reference="NCC 2022 J4D")


def _three():
    """ModelingOutput requires >=3 scenarios: baseline + 2 retrofits."""
    return [_baseline(), _heat_pump(), _glazing()]


def _state(scenarios, *, emit=None, floor_area=511.0):
    base = next(s for s in scenarios if s.name == "baseline")
    return {
        "idf_path": "data/reference_buildings/RefBldgSmallOffice.idf",
        "epw_path": "data/reference_buildings/weather/AUS_NSW_Sydney.epw",
        "modeling_output": ModelingOutput(
            scenarios=scenarios, baseline_scenario=base, modeling_confidence=0.8),
        "building_context": SimpleNamespace(floor_area_m2=floor_area),
        "emit": emit,
    }


# ── Tests ──────────────────────────────────────────────────────────────────
def test_happy_path_all_scenarios():
    fake = FakeCaller()
    out = sim_runner(_state(_three()), caller=fake)["sim_output"]

    assert isinstance(out, SimRunnerOutput)
    assert {r.scenario_name for r in out.results} == {"baseline", "heat_pump", "glazing"}
    assert out.baseline_result.scenario_name == "baseline"
    for r in out.results:
        assert r.simulation_status == "success"
        assert len(r.monthly_energy_kwh) == 12
        assert r.annual_energy_kwh == 50_000.0
        assert r.annual_eui == 97.8
        assert r.energy_end_uses == {"Heating": 12_000.0, "Cooling": 8_000.0}
        assert r.simulation_runtime_seconds == 12.3


def test_baseline_runs_unmodified():
    """Baseline has no modifications → modify_idf_component called once total
    (only the heat_pump's single mod), and baseline is still cloned + run."""
    fake = FakeCaller()
    sim_runner(_state(_three()), caller=fake)
    assert fake.count("modify_idf_component") == 2   # heat_pump + glazing, 1 mod each
    assert fake.count("clone_idf") == 3              # all three scenarios cloned
    assert fake.count("run_simulation") == 3


def test_eui_uses_building_context_floor_area():
    fake = FakeCaller()
    sim_runner(_state(_three(), floor_area=742.0), caller=fake)
    eui_calls = [kw for n, kw in fake.calls if n == "get_eui"]
    assert eui_calls and eui_calls[0]["floor_area_m2"] == 742.0


def test_failed_simulation_is_marked_not_crashed():
    fake = FakeCaller(statuses=["failed"])
    out = sim_runner(_state(_three()), caller=fake)["sim_output"]
    for r in out.results:
        assert r.simulation_status == "failed"
        assert r.monthly_energy_kwh == [0.0] * 12   # zeros, never faked
        assert r.annual_energy_kwh == 0.0


def test_poll_waits_for_success(monkeypatch):
    """running → running → success across three polls (no real sleeping)."""
    async def _no_sleep(*_a, **_k):
        return None
    monkeypatch.setattr("agents.sim_runner.asyncio.sleep", _no_sleep)

    fake = FakeCaller(statuses=["running", "running", "success"])
    out = sim_runner(_state(_three()), caller=fake)["sim_output"]
    # Scenario 1 polls 3x (running, running, success); the shared status
    # sequence then clamps to "success", so scenarios 2 & 3 poll once each.
    assert all(r.simulation_status == "success" for r in out.results)
    assert fake.count("get_simulation_status") == 5


def test_clone_error_marks_scenario_failed():
    fake = FakeCaller(fail_tool="clone_idf")
    out = sim_runner(_state(_three()), caller=fake)["sim_output"]
    assert all(r.simulation_status == "failed" for r in out.results)
    assert fake.count("run_simulation") == 0   # never reached the sim


def test_short_monthly_profile_fails_calibration_guard():
    """Sim 'succeeds' but the monthly profile isn't 12 values → failed, so the
    Reviewer's GL14 calibration can't be fed garbage."""
    fake = FakeCaller(monthly=[1_000.0] * 6)   # only 6 months
    out = sim_runner(_state(_three()), caller=fake)["sim_output"]
    assert all(r.simulation_status == "failed" for r in out.results)


def test_output_contract_feeds_real_analyzer():
    """The SimRunnerOutput contract is unchanged → the real Analyzer still runs."""
    from agents.analyzer import analyzer as real_analyzer

    fake = FakeCaller()
    state = _state(_three())
    state = sim_runner(state, caller=fake)
    state["analysis_context"] = {
        "scenario_costs": {"heat_pump": 42_000, "glazing": 28_000},
        "tariff_aud_per_kwh": 0.30, "carbon_factor_kg_per_kwh": 0.66,
        "tariff_source": "demo", "emission_factor_source": "NGA 2025 NSW",
    }
    state = real_analyzer(state)
    assert isinstance(state["analysis"], AnalyzerOutput)
    assert len(state["analysis"].analyses) >= 1


def test_emit_events_fire():
    events = []
    fake = FakeCaller()
    state = _state(_three(),
                   emit=lambda a, s, p: events.append((a, s)))
    sim_runner(state, caller=fake)
    kinds = {s for a, s in events if a == "sim_runner"}
    assert {"started", "completed"} <= kinds


# ── Envelope unwrap (transport + ToolResponse) ─────────────────────────────
def test_unwrap_strips_toolresponse_envelope():
    wrapped = {"schema_version": "1.0.0", "tool_name": "clone_idf",
               "timestamp": "2026-06-10T00:00:00Z",
               "data": {"cloned_path": "/work/x.idf"}}
    assert _unwrap(wrapped) == {"cloned_path": "/work/x.idf"}


def test_unwrap_handles_callresult_objects():
    obj = SimpleNamespace(structured_content={
        "tool_name": "run_simulation", "data": {"job_id": "x-1", "status": "running"}})
    assert _unwrap(obj) == {"job_id": "x-1", "status": "running"}


def test_unwrap_handles_content_text_blocks():
    import json
    block = SimpleNamespace(text=json.dumps(
        {"tool_name": "get_eui", "data": {"eui_kwh_m2": 100.0}}))
    obj = SimpleNamespace(content=[block])
    assert _unwrap(obj) == {"eui_kwh_m2": 100.0}
