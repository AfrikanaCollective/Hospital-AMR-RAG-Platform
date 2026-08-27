"""LangGraph graph definition (ARCH §10.1).

Phase 3 builds the actual `StateGraph`. This module fixes the node names and
edges so the topology is reviewable now and tests can assert it.

Flow:
  orchestrator --(scope_boundary / capability_not_enabled)--> escalation
  orchestrator --scope_1--> retrieval
  orchestrator --scope_2--> patient_record --> (stage_classifier | missing_info)
  retrieval [+ stage/missing] --> guideline_synthesis --> citation_verifier
  citation_verifier --pass--> orchestrator(assemble + disclaimer) --> END
  citation_verifier --fail/weak/scope--> escalation --> review queue / notify

  local_adaptation : STUB node, always returns capability_not_enabled
  next_step_recommender : RESERVED name, NOT added to the runtime graph
"""

from __future__ import annotations

NODES: tuple[str, ...] = (
    "orchestrator",
    "retrieval",
    "patient_record",
    "stage_classifier",
    "missing_info",
    "guideline_synthesis",
    "citation_verifier",
    "escalation",
    "local_adaptation",  # stub node (ARCH-026)
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


def build_graph(*_args: object, **_kwargs: object) -> object:
    raise NotImplementedError(
        "Phase 3: assemble langgraph.StateGraph(GraphState) with the Postgres "
        "checkpointer and per-node tool allow-lists (ARCH-016)."
    )
