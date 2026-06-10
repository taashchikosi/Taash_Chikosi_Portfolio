"""LangGraph supervisor — wires the 5 agents into a stateful, auditable graph.

Flow (project plan §2):
    retriever → modeler → [HITL approve] → sim_runner → analyzer → reviewer
    reviewer --calibration fail--> modeler   (adjust model inputs, re-sim)
    reviewer --claim/citation fail--> analyzer (re-verify)
    reviewer --ok--> END

Phase 2 builds the real graph with langgraph. This module defines the shared
state and the conditional routing so agents can be developed against a stable
contract. HITL is an interrupt before sim_runner.
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from verification.pydantic_schemas import (
    AnalyzerOutput, BuildingContext, ModelingOutput, ReviewResult, SimRunnerOutput,
)

MAX_CYCLES = 3


class RunState(TypedDict, total=False):
    run_id: str
    idf_path: str
    epw_path: str
    raw_utility: dict           # 12 monthly kWh + cost + tariff
    building_context: BuildingContext
    modeling_output: ModelingOutput
    approved: bool              # set True by HITL gate
    sim_output: SimRunnerOutput
    analysis: AnalyzerOutput
    review: ReviewResult
    cycle_count: int
    emit: Callable[[str, str, dict], None]   # (agent, status, payload) → SSE


def route_after_review(state: RunState) -> str:
    """Conditional edge out of the Reviewer node."""
    review = state.get("review")
    if review is None:
        return "analyzer"
    if review.approved:
        return "done"
    if state.get("cycle_count", 0) >= MAX_CYCLES:
        return "human"
    return review.route_to   # "modeler" (calibration) or "analyzer" (claim/citation)


# Node order for the linear (happy) path — used by the FastAPI runner in Phase 2
PIPELINE: list[str] = [
    "retriever", "modeler", "await_approval",
    "sim_runner", "analyzer", "reviewer",
]


def build_graph(nodes: dict[str, Callable[[RunState], RunState]]):
    """Assemble the LangGraph StateGraph. Phase 2 fills this in.

    `nodes` maps each name in PIPELINE (+ reviewer routing targets) to its
    agent callable. Kept as a factory so tests can inject stubs.
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pip install langgraph") from exc

    g = StateGraph(RunState)
    for name in ("retriever", "modeler", "sim_runner", "analyzer", "reviewer"):
        g.add_node(name, nodes[name])

    g.set_entry_point("retriever")
    g.add_edge("retriever", "modeler")
    # HITL interrupt happens before sim_runner (handled by the runner, not an edge)
    g.add_edge("modeler", "sim_runner")
    g.add_edge("sim_runner", "analyzer")
    g.add_edge("analyzer", "reviewer")
    g.add_conditional_edges("reviewer", route_after_review, {
        "modeler": "modeler",
        "analyzer": "analyzer",
        "done": END,
        "human": END,
    })
    return g.compile(interrupt_before=["sim_runner"])  # HITL gate
