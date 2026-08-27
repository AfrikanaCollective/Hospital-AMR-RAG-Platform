"""Patient-record agent (ARCH §10.2; PRD-021, PRD-084).

Does: given patient_id + purpose + the matched guideline's required fields,
return the MINIMUM authorized structured features. Every read is audit-logged
with the exact field list. Surfaces internal record contradictions as a
phi_ambiguity escalation rather than picking a value.
Does NOT: retrieve guidelines; classify; recommend; return unrequested fields.
Access: records schema for the ONE patient_id, filtered by
record_field_policy(role, purpose). The only agent with PHI field access.
Tools: list_record_fields (names only), get_patient_fields(patient_id, paths, purpose).
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (ARCH §10.2, ARCH-034)")
