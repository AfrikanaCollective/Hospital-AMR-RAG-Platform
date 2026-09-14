"""Query endpoint (SCOPE-1.1, SCOPE-2.1, SCOPE-2.2; PRD-011..PRD-016, PRD-107).

POST /query
  Body: QueryRequest (question, optional conversation_id, optional patient_id,
        purpose-of-use via header).
  Flow: orchestrator scope-classifies -> retrieval -> [patient-record
        -> stage-classifier / missing-info] -> synthesis -> citation-verifier
        grounding gate -> assemble + disclaimer OR escalate
        (app.agents.graph.build_graph).
  Never returns an ungrounded answer (PRD-NFR-2). SCOPE-2.3/2.4 intent ->
  escalation with trigger_code=scope_boundary (never answered).

The compiled graph is a process-lifetime singleton, built lazily on first
call to `_invoke_graph` — never at import time, so importing this module in
tests never opens a real Postgres connection for the checkpointer.
`_GRAPH_INVOKE_FN` is the indirection point tests monkeypatch to bypass the
real graph (and therefore real DB/Qdrant/LLM) entirely.

`Principal.user_id` -> UUID: see `app.api.deps.principal_uuid` (DEVIATIONS.md #75).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, get_db, principal_uuid, purpose_of_use
from app.memory.conversation import append_message, create_conversation
from app.schemas.citation import Citation
from app.schemas.enums import ObservedOutcome
from app.schemas.query import AnswerSegment, EscalationInfo, QueryRequest, QueryResponse

router = APIRouter()

_GRAPH: Any = None


def _invoke_graph(initial_state: dict, thread_id: str) -> dict:
    global _GRAPH  # noqa: PLW0603 - process-lifetime singleton; see module docstring
    if _GRAPH is None:
        # Deferred: building the graph opens the real Postgres checkpointer
        # connection (app.memory.checkpointer.get_checkpointer) — must not
        # happen at module import time.
        from app.agents.graph import build_graph  # noqa: PLC0415

        _GRAPH = build_graph()
    return _GRAPH.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})


_GRAPH_INVOKE_FN = _invoke_graph


@router.post("", response_model=QueryResponse)
async def submit_query(
    body: QueryRequest,
    principal: Principal = Depends(current_principal),
    purpose: str = Depends(purpose_of_use),
    session: Session = Depends(get_db),
) -> QueryResponse:
    user_id = principal_uuid(principal)
    if body.conversation_id:
        conversation_id = uuid.UUID(body.conversation_id)
    else:
        patient_id = uuid.UUID(body.patient_id) if body.patient_id else None
        conversation = create_conversation(session, user_id=user_id, patient_id=patient_id)
        conversation_id = conversation.id

    append_message(session, conversation_id, turn=1, role="user", content=body.question)

    initial_state = {
        "conversation_id": str(conversation_id),
        "user_id": str(user_id),
        "roles": list(principal.roles),
        "purpose": purpose,
        "patient_id": body.patient_id,
        "query": body.question,
        "hospital_constraint": body.hospital_constraint,
    }
    try:
        out = _GRAPH_INVOKE_FN(initial_state, str(conversation_id))
    except Exception as exc:  # noqa: BLE001 - never surface an internal error as a clinical answer
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The query pipeline failed unexpectedly."
        ) from exc

    message_id = uuid.uuid4()
    escalation_info = None
    segments: list[AnswerSegment] = []
    citations: list[Citation] = []
    observed_outcome = out.get("observed_outcome") or ObservedOutcome.ESCALATED

    if out.get("escalation"):
        esc = out["escalation"]
        escalation_info = EscalationInfo(
            escalation_id=str(esc.get("escalation_id", "")),
            trigger_code=esc["trigger_code"],
            message=esc.get("message", ""),
        )
        observed_outcome = ObservedOutcome.ESCALATED
        append_message(
            session,
            conversation_id,
            turn=2,
            role="assistant",
            content=f"[escalated: {esc.get('trigger_code')}] {esc.get('message', '')}",
            hitl_ref=uuid.UUID(str(esc["escalation_id"])) if esc.get("escalation_id") else None,
        )
    else:
        final = out.get("final_answer") or {}
        segments = [AnswerSegment(**seg) for seg in final.get("segments", [])]
        citations = [Citation(**c) for c in final.get("citations", [])]
        append_message(
            session,
            conversation_id,
            turn=2,
            role="assistant",
            content="\n".join(s.text for s in segments),
            citations=[c.model_dump(mode="json") for c in citations],
            retrieved_chunk_ids=[
                {"chunk_id": item["chunk_id"], "score": item["score"]}
                for item in out.get("retrieval") or []
            ],
            grounding=out.get("grounding_report") or {},
        )

    return QueryResponse(
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        observed_outcome=observed_outcome,
        scope_label=out["scope_label"],
        segments=segments,
        citations=citations,
        escalation=escalation_info,
    )
