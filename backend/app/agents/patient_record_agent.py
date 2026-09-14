"""Patient-record agent (ARCH §10.2; PRD-021, PRD-084).

Does: given patient_id + purpose + the matched guideline's required fields,
return the MINIMUM authorized structured features. Every read is audit-logged
with the exact field list. Surfaces internal record contradictions as a
phi_ambiguity escalation rather than picking a value.
Does NOT: retrieve guidelines; classify; recommend; return unrequested fields.
Access: records schema for the ONE patient_id, filtered by
record_field_policy(role, purpose). The only agent with PHI field access.
Tools: list_record_fields (names only), get_patient_fields(patient_id, paths, purpose).

Field-level policy: see `app.records.access` module docstring (DEVIATIONS.md
#70, #87) — `get_patient_fields` now gates every field through the DB-backed
`record_field_policy(role, purpose, field)` table. `_select_actor_role`
(DEVIATIONS.md #87) picks `"clinician"` when the principal holds it (this
agent's access is clinical-care field access; `/query` already requires the
`clinician` role — `ROUTE_PERMISSIONS["query:submit"]`), falling back to the
lexicographically-first role otherwise — never `state["roles"][0]` directly,
since `Principal.roles` is a `frozenset` and its iteration order is
per-process hash-dependent, not a meaningful priority; that ambiguity was
harmless while `actor_role` was audit-log-only, but is now access-determining.

Opens its own session scoped to `patient_id` (`_SESSION_SCOPE(patient_scope=...)`,
DEVIATIONS.md #88) — the Postgres row-level-security GUC that restricts
`records.patient`/`records.patient_record`/`memory.patient_context` reads to
this one patient for the lifetime of the session, defense-in-depth beneath
the `record_field_policy` gate above.

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


def _select_actor_role(roles: list[str] | None) -> str | None:
    """Deterministic role choice for field-policy gating (DEVIATIONS.md #87)
    — prefer `clinician` (this agent's own access purpose) when the
    principal holds it; otherwise the lexicographically-first role, never an
    arbitrary `frozenset` iteration order."""
    if not roles:
        return None
    if "clinician" in roles:
        return "clinician"
    return sorted(roles)[0]


def run(state: GraphState) -> GraphState:
    patient_id_raw = state.get("patient_id")
    if not patient_id_raw:
        state["escalation"] = {
            "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
            "message": "No patient is attached to this request; cannot fetch patient features.",
        }
        return state
    patient_id = uuid.UUID(patient_id_raw)

    actor_role = _select_actor_role(state.get("roles"))
    with _SESSION_SCOPE(patient_scope=str(patient_id)) as session:
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
