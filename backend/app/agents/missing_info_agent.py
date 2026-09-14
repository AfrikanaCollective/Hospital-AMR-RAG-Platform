"""Missing-info agent (SCOPE-2.2; ARCH §10.2, §9.2).

Does: diff patient_features / records.field_index against the fields the matched
guideline(s) require; output a specific missing-item list, each cited to the
requiring text. Clarification-seeking only — low risk.
Does NOT: recommend; guess values; proceed without the info.
Access: records.field_index (names), authorized field values, Qdrant (matched guideline).
Tools: list_record_fields, get_patient_fields, get_chunk, emit_missing_info.

Required fields come from the same retrieved `criteria` chunks the
stage-classifier uses (ARCH §6 rule 4): each criterion's `field` maps onto a
patient-feature path via `app.records.criteria.map_criterion_field`
(DEVIATIONS.md #71) — that mapping IS the "why this field is needed" citation
back to the requiring text (the criteria chunk itself). Presence is checked
against `field_index` ONLY (never decrypts) via
`app.records.access.get_record_field_index` /
`app.records.criteria.field_present_in_index` — a genuinely missing field
never requires touching PHI to detect.

**Not an escalation (DEVIATIONS.md #76):** unlike the stage-classifier's
`stage_classification_uncertain`, finding missing fields here does NOT raise
`state["escalation"]`. ARCH §9.2 frames SCOPE-2.2 as "clarification-seeking...
low-risk... keep it in scope" — a released, cited "here is what's missing"
answer, not something that needs to be held for clinician review before the
clinician even sees the question. `state["missing_info"]` feeds
`guideline_synthesis_agent`'s `scope2_context` so the released answer reports
both what the retrieved criteria require and what's missing, in the normal
reported-content framing. The `missing_critical_info` trigger code (still
"held" in `app.hitl.triggers.RELEASE_POLICY`) remains defined for a stronger
future case this agent doesn't currently produce.

This agent also runs its own retrieval (SCOPE-2.2 never reaches
`retrieval_agent` directly — ARCH §10.1's fixed graph edges route
orchestrator -> patient_record -> missing_info, not through retrieval) and
populates `state["retrieval"]` / `state["retrieval_confidence"]` from it, same
as `stage_classifier_agent`, so `guideline_synthesis_agent`'s SOURCES and
confidence gate downstream see real data instead of nothing.
"""

from __future__ import annotations

import uuid

from app.agents.state import GraphState
from app.db.session import session_scope
from app.records.access import PatientNotFoundError, get_record_field_index
from app.records.criteria import field_present_in_index, map_criterion_field
from app.retrieval.hybrid import retrieve
from app.schemas.enums import EscalationTrigger

_RETRIEVE_FN = retrieve
_SESSION_SCOPE = session_scope
_FIELD_INDEX_FN = get_record_field_index


def run(state: GraphState) -> GraphState:
    patient_id_raw = state.get("patient_id")
    if not patient_id_raw:
        state["escalation"] = {
            "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
            "message": "No patient is attached to this request; cannot assess missing information.",
        }
        return state
    patient_id = uuid.UUID(patient_id_raw)

    with _SESSION_SCOPE() as session:
        items, snapshot = _RETRIEVE_FN(state["query"], session=session)
        try:
            field_index = _FIELD_INDEX_FN(session, patient_id)
        except PatientNotFoundError:
            state["escalation"] = {
                "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
                "message": "No ingested record was found for the attached patient.",
            }
            return state

    state["retrieval"] = items
    state["retrieval_confidence"] = {
        **snapshot["confidence"],
        "conflicts": snapshot.get("conflicts", []),
    }

    criteria_items = [i for i in items if i.get("chunk_type") == "criteria"]

    missing: list[dict] = []
    seen_paths: set[str] = set()
    for item in criteria_items:
        criteria = (item.get("meta") or {}).get("criteria") or []
        for criterion in criteria:
            field_text = criterion.get("field", "")
            path = map_criterion_field(field_text)
            if path is None or path in seen_paths:
                continue
            if not field_present_in_index(field_index, path):
                seen_paths.add(path)
                missing.append(
                    {
                        "field": path,
                        "why": (
                            f"required by the criterion {field_text!r} "
                            f"{criterion.get('operator', '')} {criterion.get('value', '')}"
                        ),
                        "citation_id": item["chunk_id"],
                    }
                )

    state["missing_info"] = missing
    return state
