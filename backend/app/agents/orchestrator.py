"""Orchestrator / supervisor agent (ARCH §10.2).

Does: scope-classify the query; route to sub-agents; assemble the final
response; inject the non-removable disclaimer (ARCH-037); own the
escalate-vs-release decision; enforce the segment structure (ARCH §8.2).
Does NOT: retrieve; read PHI values; generate guideline claims; resolve
source conflicts.
Access: memory.conversation, hitl.escalation (write), patient_id handle only.
Tools: classify_scope, dispatch, assemble_response, apply_disclaimer, open_escalation.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (ARCH §10.2, ARCH-025, ARCH-037)")
