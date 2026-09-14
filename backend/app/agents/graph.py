"""LangGraph graph definition (ARCH §10.1).

Fixes the node names and edges so the topology is reviewable and tests can
assert it (unchanged from Phase 1). `build_graph()` assembles the real
`langgraph.graph.StateGraph`.

Flow:
  orchestrator --(scope_boundary / capability_not_enabled)--> escalation
  orchestrator --scope_1--> retrieval
  orchestrator --scope_2--> patient_record --> (stage_classifier | missing_info)
  retrieval [+ stage/missing] --> guideline_synthesis --> citation_verifier
  citation_verifier --pass--> orchestrator(assemble + disclaimer) --> END
  citation_verifier --fail/weak/scope--> escalation --> review queue / notify

  local_adaptation : STUB node, always returns capability_not_enabled — NOT
    wired into this graph (ARCH-026: extension seam, no runtime logic; wiring
    an unreachable stub node into a compiled graph would be dead code).
  next_step_recommender : RESERVED name, NOT added to the runtime graph

Routing (ARCH §10.1) is deterministic code over `GraphState`, never a model
call — see `_route_from_orchestrator` / `_route_after_patient_record` /
`_route_after_citation_verifier` below. Every non-orchestrator node that can
raise an escalation (`patient_record`, `stage_classifier`, `missing_info`)
still has an unconditional edge to `guideline_synthesis` (matching `EDGES`
below); `guideline_synthesis` and `citation_verifier` both short-circuit
(pass through unchanged) when `state["escalation"]` is already set, so the
escalation set upstream survives untouched to `_route_after_citation_verifier`
without those nodes re-deciding anything (DEVIATIONS.md #74).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import (
    citation_verifier_agent,
    escalation_agent,
    guideline_synthesis_agent,
    missing_info_agent,
    orchestrator,
    patient_record_agent,
    retrieval_agent,
    stage_classifier_agent,
)
from app.agents.state import GraphState
from app.schemas.enums import ScopeLabel

NODES: tuple[str, ...] = (
    "orchestrator",
    "retrieval",
    "patient_record",
    "stage_classifier",
    "missing_info",
    "guideline_synthesis",
    "citation_verifier",
    "escalation",
    "local_adaptation",  # stub node (ARCH-026); not wired into the runtime graph
)

# next_step_recommender is deliberately NOT in NODES (reserved interface only).

EDGES: tuple[tuple[str, str], ...] = (
    ("orchestrator", "retrieval"),
    ("orchestrator", "patient_record"),
    ("orchestrator", "escalation"),
    ("patient_record", "stage_classifier"),
    ("patient_record", "missing_info"),
    ("retrieval", "guideline_synthesis"),
    ("stage_classifier", "guideline_synthesis"),
    ("missing_info", "guideline_synthesis"),
    ("guideline_synthesis", "citation_verifier"),
    ("citation_verifier", "orchestrator"),
    ("citation_verifier", "escalation"),
)

_RUNTIME_NODES = tuple(n for n in NODES if n != "local_adaptation")


def _route_from_orchestrator(state: GraphState) -> str:
    if "final_answer" in state:
        return "END"
    label = state["scope_label"]
    if label == ScopeLabel.SCOPE_1:
        return "retrieval"
    if label in (ScopeLabel.SCOPE_2_STAGE, ScopeLabel.SCOPE_2_MISSING_INFO):
        return "patient_record"
    return "escalation"  # SCOPE_2_EXCLUDED, or any other state that escalated


def _route_after_patient_record(state: GraphState) -> str:
    if state.get("escalation"):
        return "escalation"
    if state["scope_label"] == ScopeLabel.SCOPE_2_STAGE:
        return "stage_classifier"
    return "missing_info"


def _route_after_citation_verifier(state: GraphState) -> str:
    return "escalation" if state.get("escalation") else "orchestrator"


def build_graph(*, checkpointer: Any = None) -> Any:
    """Assemble the compiled `StateGraph`. `checkpointer` defaults to
    `app.memory.checkpointer.get_checkpointer()` (real Postgres) when not
    given; pass `langgraph.checkpoint.memory.MemorySaver()` for offline
    tests/dev runs that don't need cross-process durability."""
    if checkpointer is None:
        # Deferred: avoids importing langgraph-checkpoint-postgres (and its
        # psycopg driver) for every caller that passes its own checkpointer.
        from app.memory.checkpointer import get_checkpointer  # noqa: PLC0415

        checkpointer = get_checkpointer()

    graph = StateGraph(GraphState)
    graph.add_node("orchestrator", orchestrator.run)
    graph.add_node("retrieval", retrieval_agent.run)
    graph.add_node("patient_record", patient_record_agent.run)
    graph.add_node("stage_classifier", stage_classifier_agent.run)
    graph.add_node("missing_info", missing_info_agent.run)
    graph.add_node("guideline_synthesis", guideline_synthesis_agent.run)
    graph.add_node("citation_verifier", citation_verifier_agent.run)
    graph.add_node("escalation", escalation_agent.run)

    graph.set_entry_point("orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        _route_from_orchestrator,
        {
            "retrieval": "retrieval",
            "patient_record": "patient_record",
            "escalation": "escalation",
            "END": END,
        },
    )
    graph.add_edge("retrieval", "guideline_synthesis")
    graph.add_conditional_edges(
        "patient_record",
        _route_after_patient_record,
        {
            "stage_classifier": "stage_classifier",
            "missing_info": "missing_info",
            "escalation": "escalation",
        },
    )
    graph.add_edge("stage_classifier", "guideline_synthesis")
    graph.add_edge("missing_info", "guideline_synthesis")
    graph.add_edge("guideline_synthesis", "citation_verifier")
    graph.add_conditional_edges(
        "citation_verifier",
        _route_after_citation_verifier,
        {"escalation": "escalation", "orchestrator": "orchestrator"},
    )
    graph.add_edge("escalation", END)

    return graph.compile(checkpointer=checkpointer)
