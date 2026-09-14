"""Shared `/query` pipeline logic (ARCH §8.2; PRD-011..PRD-016; ARCH-035).

Split out of `app.api.routes.query` (DEVIATIONS.md #94) so the exact same
persistence + audit + response-assembly logic backs both the synchronous
route and the async Celery task (`app.agents.tasks.run_query`) — one place
defines what "the pipeline ran" means, not two copies that can drift.

- `prepare_query`: create/resolve the conversation, persist the user's turn,
  write the `query` audit event (the *attempt*, recorded immediately whether
  the run that follows is synchronous or handed to Celery).
- `assemble_and_persist_response`: given the compiled graph's raw output,
  persist the assistant turn, write the `answer` audit event, and build the
  `QueryResponse` the caller ultimately sees.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from app.audit.log import write_event
from app.memory.conversation import append_message, create_conversation
from app.schemas.citation import Citation
from app.schemas.enums import ObservedOutcome
from app.schemas.query import AnswerSegment, EscalationInfo, QueryResponse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ROLE = "clinician"  # /query and /query/async are both require_role(ROLE)-gated


def prepare_query(
    session: Session,
    *,
    question: str,
    conversation_id: str | None,
    patient_id: str | None,
    user_id: uuid.UUID,
    purpose: str,
) -> uuid.UUID:
    """Resolve/create the conversation, persist the user's turn, audit the
    attempt. Returns the conversation id every subsequent step keys off."""
    if conversation_id:
        resolved_id = uuid.UUID(conversation_id)
    else:
        conversation = create_conversation(
            session,
            user_id=user_id,
            patient_id=uuid.UUID(patient_id) if patient_id else None,
        )
        resolved_id = conversation.id

    append_message(session, resolved_id, turn=1, role="user", content=question)

    write_event(
        session,
        action="query",
        actor_id=user_id,
        actor_role=ROLE,
        purpose=purpose,
        conversation_id=resolved_id,
        patient_id=uuid.UUID(patient_id) if patient_id else None,
        query_hash=hashlib.sha256(question.encode("utf-8")).hexdigest(),
    )
    return resolved_id


def assemble_and_persist_response(
    session: Session,
    out: dict,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
) -> QueryResponse:
    """Given the compiled graph's raw output: persist the assistant turn,
    write the `answer` audit event, and build the `QueryResponse`."""
    message_id = uuid.uuid4()
    escalation_info = None
    segments: list[AnswerSegment] = []
    citations: list[Citation] = []
    answer_text: str | None = None
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
        answer_text = "\n".join(s.text for s in segments)
        append_message(
            session,
            conversation_id,
            turn=2,
            role="assistant",
            content=answer_text,
            citations=[c.model_dump(mode="json") for c in citations],
            retrieved_chunk_ids=[
                {"chunk_id": item["chunk_id"], "score": item["score"]}
                for item in out.get("retrieval") or []
            ],
            grounding=out.get("grounding_report") or {},
        )

    write_event(
        session,
        action="answer",
        actor_id=user_id,
        actor_role=ROLE,
        purpose=purpose,
        conversation_id=conversation_id,
        model_id=out.get("model_id"),
        response_hash=hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
        if answer_text is not None
        else None,
        grounding_summary=out.get("grounding_report"),
        outcome=str(
            observed_outcome.value if hasattr(observed_outcome, "value") else observed_outcome
        ),
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
