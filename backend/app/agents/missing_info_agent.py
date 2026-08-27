"""Missing-info agent (SCOPE-2.2; ARCH §10.2, §9.2).

Does: diff patient_features / records.field_index against the fields the matched
guideline(s) require; output a specific missing-item list, each cited to the
requiring text. Clarification-seeking only — low risk.
Does NOT: recommend; guess values; proceed without the info.
Access: records.field_index (names), authorized field values, Qdrant (matched guideline).
Tools: list_record_fields, get_patient_fields, get_chunk, emit_missing_info.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (SCOPE-2.2, ARCH §9.2)")
