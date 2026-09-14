"""Patient-record agent (ARCH §10.2; PRD-021, PRD-084).

Does: given patient_id + purpose + the matched guideline's required fields,
return the MINIMUM authorized structured features. Every read is audit-logged
with the exact field list. Surfaces internal record contradictions as a
phi_ambiguity escalation rather than picking a value.
Does NOT: retrieve guidelines; classify; recommend; return unrequested fields.
Access: records schema for the ONE patient_id, filtered by
record_field_policy(role, purpose). The only agent with PHI field access.
Tools: list_record_fields (names only), get_patient_fields(patient_id, paths, purpose).

Field-level policy scope: see app.records.access module docstring
(DEVIATIONS.md #70) — Phase 3 enforces minimization + full audit coverage,
not yet the DB-backed (role, purpose, field) policy table (Phase 4).

`state["required_field_paths"]`, when set by the orchestrator from a matched
guideline's criteria (SCOPE-2.1) or from the missing-info agent's own
required-field derivation (SCOPE-2.2), narrows what is fetched. When absent,
this agent fetches every field the patient's own record actually has (via
`list_record_fields`) — still the minimum available, just not narrowed to a
specific guideline's needs yet (the case on first entry into a SCOPE-2 flow,
before a guideline has been matched).
"""

from __future__ import annotations

import uuid

from app.agents.state import GraphState
from app.db.session import session_scope
from app.records.access import PatientNotFoundError, get_patient_fields, list_record_fields
from app.schemas.enums import EscalationTrigger

_SESSION_SCOPE = session_scope
_LIST_FIELDS_FN = list_record_fields
_GET_FIELDS_FN = get_patient_fields


def run(state: GraphState) -> GraphState:
    patient_id_raw = state.get("patient_id")
    if not patient_id_raw:
        state["escalation"] = {
            "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
            "message": "No patient is attached to this request; cannot fetch patient features.",
        }
        return state
    patient_id = uuid.UUID(patient_id_raw)

    roles = state.get("roles")
    actor_role = roles[0] if roles else None
    with _SESSION_SCOPE() as session:
        try:
            wanted = state.get("required_field_paths") or _LIST_FIELDS_FN(session, patient_id)
            features = _GET_FIELDS_FN(
                session,
                patient_id,
                list(wanted),
                purpose=state.get("purpose") or "clinical_care",
                actor_id=uuid.UUID(state["user_id"]) if state.get("user_id") else None,
                actor_role=actor_role,
                conversation_id=uuid.UUID(state["conversation_id"])
                if state.get("conversation_id")
                else None,
            )
        except PatientNotFoundError:
            state["escalation"] = {
                "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
                "message": "No ingested record was found for the attached patient.",
            }
            return state

    state["patient_features"] = features
    return state
