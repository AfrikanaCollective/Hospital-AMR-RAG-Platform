"""HITL escalation + accept-axis endpoints (PRD-030, PRD-032, PRD-033; ARCH §12, §13).

GET  /hitl/escalations/{id}
POST /hitl/escalations/{id}/decision   (reviewer)  -> full_accept | partial_accept | reject
      Effects on shown answer / conversation memory / patient_context per ARCH §13.2.
Every decision writes an immutable audit_event and updates escalation + queue state.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, principal_uuid, require_role
from app.crypto.provider import get_crypto
from app.db.models.hitl import Escalation
from app.hitl.decisions import apply_decision
from app.hitl.escalation import EscalationNotFoundError, get_escalation
from app.schemas.hitl import HitlDecisionRequest

router = APIRouter()

_AAD_NAMESPACE = b"escalation-candidate-answer:"


def _decrypt_candidate_answer(escalation: Escalation) -> str | None:
    if escalation.candidate_answer_enc is None:
        return None
    crypto = get_crypto()
    return crypto.decrypt(
        escalation.candidate_answer_enc, aad=_AAD_NAMESPACE + str(escalation.id).encode("utf-8")
    ).decode("utf-8")


@router.get("/escalations/{escalation_id}")
async def get_escalation_detail(
    escalation_id: str,
    session: Session = Depends(get_db),
    _principal: Principal = Depends(require_role("reviewer", "admin")),
) -> dict:
    try:
        escalation = get_escalation(session, uuid.UUID(escalation_id))
    except EscalationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {
        "id": str(escalation.id),
        "conversation_id": str(escalation.conversation_id) if escalation.conversation_id else None,
        "trigger_code": escalation.trigger_code,
        "trigger_detail": escalation.trigger_detail,
        "candidate_answer": _decrypt_candidate_answer(escalation),
        "state": escalation.state,
        "resolution": escalation.resolution,
        "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
    }


@router.post("/escalations/{escalation_id}/decision")
async def submit_decision(
    escalation_id: str,
    body: HitlDecisionRequest,
    session: Session = Depends(get_db),
    principal: Principal = Depends(require_role("reviewer")),
) -> dict:
    try:
        decision = apply_decision(
            session,
            escalation_id=uuid.UUID(escalation_id),
            reviewer_id=principal_uuid(principal),
            action=body.action,
            edited_answer=body.edited_answer,
            span_actions=[s.model_dump() for s in body.span_actions],
            accepted_context_ids=body.accepted_context_ids,
            reason_code=body.reason_code,
        )
    except EscalationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"decision_id": str(decision.id), "action": decision.action}
