"""Stage-classifier agent (SCOPE-2.1; ARCH §10.2, §9.2).

Does: retrieve `criteria` chunks; evaluate extracted meta.criteria[] against
patient_features; output a stage label + confidence + citations to the criteria
+ which patient features matched. Escalate (stage_classification_uncertain) on
low confidence or multiple plausible stages.
Does NOT: recommend next steps; infer features not in the record; use
non-criteria text as authority.
Access: Qdrant (criteria filter); features from the patient-record agent.
Tools: hybrid_search, get_chunk, evaluate_criteria, emit_classification.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (SCOPE-2.1, ARCH §9.2)")
