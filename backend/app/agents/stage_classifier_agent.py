"""Stage-classifier agent (SCOPE-2.1; ARCH §10.2, §9.2).

Does: retrieve `criteria` chunks; evaluate extracted meta.criteria[] against
patient_features; output a stage label + confidence + citations to the criteria
+ which patient features matched. Escalate (stage_classification_uncertain) on
low confidence or multiple plausible stages.
Does NOT: recommend next steps; infer features not in the record; use
non-criteria text as authority.
Access: Qdrant (criteria filter); features from the patient-record agent.
Tools: hybrid_search, get_chunk, evaluate_criteria, emit_classification.

**Stage label source (DEVIATIONS.md #71):** ARCH §6 rule 4 defines
`meta.criteria[]` (field/op/value/unit) but the ingest manifest has no
operator-supplied per-chunk "this criteria set names stage X" field, and
adding one is a chunking/manifest-schema change out of scope for Phase 3. A
criteria chunk's own `heading` (the nearest section heading — e.g. "Criteria
for Stabilisation Phase", already captured at chunking time) is used as the
stage label instead: it is real, operator-authored text from the source
document, never invented by this agent. A chunk with no heading cannot anchor
a classification and is skipped.
"""

from __future__ import annotations

from app.agents.state import GraphState
from app.db.session import session_scope
from app.records.criteria import evaluate_criteria
from app.retrieval.hybrid import retrieve
from app.schemas.enums import EscalationTrigger

_RETRIEVE_FN = retrieve
_SESSION_SCOPE = session_scope

# A stage is only classified when at least this many of its criteria were
# actually evaluable (mapped to a known feature path with a present value) —
# a chunk where every criterion is uncertain cannot anchor a classification.
_MIN_EVALUATED_CRITERIA = 1


def run(state: GraphState) -> GraphState:
    features = state.get("patient_features") or {}
    with _SESSION_SCOPE() as session:
        items, snapshot = _RETRIEVE_FN(state["query"], session=session)

    # SCOPE-2.1 never reaches retrieval_agent directly (ARCH §10.1's fixed
    # EDGES route orchestrator -> patient_record -> stage_classifier, not
    # through retrieval) — this agent's own retrieval call is what
    # guideline_synthesis_agent's SOURCES + confidence gate need downstream.
    state["retrieval"] = items
    state["retrieval_confidence"] = {
        **snapshot["confidence"],
        "conflicts": snapshot.get("conflicts", []),
    }

    criteria_items = [i for i in items if i.get("chunk_type") == "criteria"]

    candidates: list[dict] = []
    for item in criteria_items:
        criteria = (item.get("meta") or {}).get("criteria") or []
        stage_label = item.get("heading")
        if not stage_label or not criteria:
            continue
        results = evaluate_criteria(criteria, features)
        evaluated = [r for r in results if r.matched is not None]
        if len(evaluated) < _MIN_EVALUATED_CRITERIA:
            continue
        candidates.append(
            {
                "stage": stage_label,
                "chunk_id": item["chunk_id"],
                "all_pass": all(r.matched for r in evaluated),
                "evaluated": evaluated,
                "missing": [r.criterion for r in results if r.matched is None],
            }
        )

    passing = [c for c in candidates if c["all_pass"]]

    if len(passing) == 1:
        winner = passing[0]
        state["stage_classification"] = {
            "stage": winner["stage"],
            "confidence": 1.0,
            "citations": [winner["chunk_id"]],
            "matched": [
                {
                    "criterion": r.criterion,
                    "feature": r.feature_path,
                    "citation_id": winner["chunk_id"],
                }
                for r in winner["evaluated"]
            ],
            "uncertain": False,
            "missing": [],
        }
        return state

    # Zero or multiple plausible stages, or nothing evaluable: uncertain —
    # never guess between candidates (ARCH §9.2 rule 4).
    missing_fields = sorted({m.get("field", "") for c in candidates for m in c["missing"]})
    state["stage_classification"] = {
        "stage": None,
        "confidence": 0.0,
        "citations": [c["chunk_id"] for c in candidates],
        "matched": [],
        "uncertain": True,
        "missing": missing_fields,
    }
    state["escalation"] = {
        "trigger_code": EscalationTrigger.STAGE_CLASSIFICATION_UNCERTAIN,
        "message": (
            "Stage of care could not be confidently classified from the retrieved "
            "criteria and the available patient features."
        ),
    }
    return state
