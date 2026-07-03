"""LangGraph supervisor — wires the 5 agents into a stateful, auditable graph.

Flow (project plan §2):
    retriever → modeler → [HITL approve] → sim_runner → analyzer → reviewer
    reviewer --baseline outside CBD cohort--> inputs   (demoer adjusts inputs, re-run)
    reviewer --claim/citation issue--> analyzer (re-verify)
    reviewer --ok--> END

This is the LIVE graph: `build_graph` compiles a real langgraph StateGraph with a
checkpointer and `interrupt_before=["sim_runner"]` — the API-enforced HITL gate.
The FastAPI driver (api/main._drive_pipeline) streams it to the first interrupt,
holds for the human approval, applies the chosen measure via `update_state`, and
resumes. Serialization rule: node callables must strip non-JSON-native values
(the `emit` callback) from returned state so checkpoints stay serializable.
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from verification.pydantic_schemas import (
    AnalyzerOutput, BuildingContext, ModelingOutput, ModelInputs, ReviewResult,
    SimRunnerOutput,
)

MAX_CYCLES = 3


class RunState(TypedDict, total=False):
    run_id: str
    idf_path: str
    epw_path: str
    raw_utility: dict           # 12 monthly kWh + cost + tariff
    model_inputs: ModelInputs   # the six editable inputs (None fields = untouched)
    building_context: BuildingContext
    modeling_output: ModelingOutput
    approved: bool              # set True by HITL gate
    validate: bool              # realism gate on/off (the demo toggle)
    analysis_context: dict      # tariff + carbon factor for the analyzer
    sim_output: SimRunnerOutput
    analysis: AnalyzerOutput
    review: ReviewResult
    cycle_count: int
    emit: Callable[[str, str, dict], None]   # (agent, status, payload) → SSE
    # NOTE: `emit` is injected per-node by the driver's wrappers and stripped from
    # returned state — it must never reach the checkpointer (not serializable).


def route_after_review(state: RunState) -> str:
    """Conditional edge out of the Reviewer node."""
    review = state.get("review")
    if review is None:
        # An absent review is an anomaly (the reviewer node always sets one).
        # Route to the terminal human edge rather than looping back through
        # analyzer→reviewer forever.
        return "human"
    if review.approved:
        return "done"
    if state.get("cycle_count", 0) >= MAX_CYCLES:
        return "human"
    # "inputs" (unrealistic baseline / floor area) is terminal — only the demoer
    # can change the model inputs; no agent re-work would fix it.
    if review.route_to == "inputs":
        return "inputs"
    return review.route_to   # "modeler" (re-model) or "analyzer" (claim/citation)


# Node order for the linear (happy) path — used by the FastAPI runner in Phase 2
PIPELINE: list[str] = [
    "retriever", "modeler", "await_approval",
    "sim_runner", "analyzer", "reviewer",
]


def build_graph(nodes: dict[str, Callable[[RunState], RunState]],
                checkpointer: Any | None = None):
    """Assemble + compile the LIVE LangGraph StateGraph.

    `nodes` maps each name in PIPELINE (+ reviewer routing targets) to its
    agent callable (sync or async — langgraph handles both). Kept as a factory
    so the API driver injects emit-wrapping nodes and tests can inject stubs.

    The compiled graph pauses BEFORE sim_runner (`interrupt_before`) — that is
    the genuine, API-enforced human approval gate: nothing simulates until the
    driver resumes the thread. A checkpointer is required for the interrupt;
    the default is an in-process MemorySaver (one thread per run_id).
    """
    try:
        from langgraph.graph import StateGraph, END
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install langgraph") from exc

    # The run state carries our pydantic models (BuildingContext, ModelingOutput,
    # SimRunnerOutput, AnalyzerOutput, ReviewResult) — allowlist them explicitly so
    # checkpoint (de)serialization stays supported as langgraph tightens msgpack.
    _serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("verification.pydantic_schemas", "CodeReference"),
        ("verification.pydantic_schemas", "UtilityData"),
        ("verification.pydantic_schemas", "BuildingContext"),
        ("verification.pydantic_schemas", "IDFModification"),
        ("verification.pydantic_schemas", "ModelInputs"),
        ("verification.pydantic_schemas", "RetrofitScenario"),
        ("verification.pydantic_schemas", "ModelingOutput"),
        ("verification.pydantic_schemas", "SimulationResult"),
        ("verification.pydantic_schemas", "SimRunnerOutput"),
        ("verification.pydantic_schemas", "RetrofitAnalysis"),
        ("verification.pydantic_schemas", "AnalyzerOutput"),
        ("verification.pydantic_schemas", "ReviewResult"),
    ])

    g = StateGraph(RunState)
    for name in ("retriever", "modeler", "sim_runner", "analyzer", "reviewer"):
        g.add_node(name, nodes[name])

    g.set_entry_point("retriever")
    g.add_edge("retriever", "modeler")
    # HITL interrupt happens before sim_runner (interrupt_before, not an edge)
    g.add_edge("modeler", "sim_runner")
    g.add_edge("sim_runner", "analyzer")
    g.add_edge("analyzer", "reviewer")
    g.add_conditional_edges("reviewer", route_after_review, {
        "inputs": END,        # demoer adjusts model inputs + re-runs
        "modeler": "modeler",
        "analyzer": "analyzer",
        "done": END,
        "human": END,
    })
    return g.compile(checkpointer=checkpointer or MemorySaver(serde=_serde),
                     interrupt_before=["sim_runner"])  # HITL gate
