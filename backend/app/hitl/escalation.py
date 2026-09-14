"""Escalation lifecycle (ARCH §12.2).

open -> in_review -> resolved (accepted | partial | rejected). All transitions
audit-logged. No reviewer within ESCALATION_SLA_MINUTES => stays open, user
sees a held state + safe templated message, NOT auto-released (DEVIATIONS.md #14).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.audit.log import write_event
from app.crypto.provider import get_crypto
from app.db.models.hitl import Escalation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

HELD_TEMPLATE = (
    "This response needs clinician review before it can be shown. "
    "No independent recommendation is available from the system."
)

_AAD_NAMESPACE = b"escalation-candidate-answer:"


class EscalationNotFoundError(LookupError):
    pass


def create_escalation(
    session: Session,
    *,
    trigger_code: str,
    trigger_detail: dict | None = None,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    candidate_answer: str | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    purpose: str | None = None,
) -> Escalation:
    escalation = Escalation(
        conversation_id=conversation_id,
        message_id=message_id,
        trigger_code=trigger_code,
        trigger_detail=trigger_detail or {},
        state="open",
    )
    session.add(escalation)
    session.flush()

    if candidate_answer is not None:
        crypto = get_crypto()
        aad = _AAD_NAMESPACE + str(escalation.id).encode("utf-8")
        escalation.candidate_answer_enc = crypto.encrypt(candidate_answer.encode("utf-8"), aad=aad)

    write_event(
        session,
        action="hitl_action",
        actor_id=actor_id,
        actor_role=actor_role,
        purpose=purpose,
        conversation_id=conversation_id,
        outcome="escalated",
        detail={"trigger_code": trigger_code, "escalation_id": str(escalation.id)},
    )
    return escalation


def get_escalation(session: Session, escalation_id: uuid.UUID) -> Escalation:
    escalation = session.get(Escalation, escalation_id)
    if escalation is None:
        raise EscalationNotFoundError(f"no escalation {escalation_id}")
    return escalation


def list_escalations(session: Session, *, state: str | None = None) -> list[Escalation]:
    """Backs `GET /hitl/escalations` (DEVIATIONS.md #97) — until now there was
    no way for a reviewer to *discover* an escalation id at all (only
    `GET /escalations/{id}`, which requires already having one). Default
    (`state=None`): everything not yet `resolved` (`open` + `in_review`) —
    "the queue a reviewer would want to pull from," matching how
    `GET /review-queue` scopes its own default. An explicit `state` filters
    to exactly that value instead."""
    stmt = select(Escalation).order_by(Escalation.created_at.asc())
    if state:
        stmt = stmt.where(Escalation.state == state)
    else:
        stmt = stmt.where(Escalation.state != "resolved")
    return list(session.execute(stmt).scalars().all())


def mark_in_review(escalation: Escalation) -> None:
    """A reviewer has opened this escalation (no independent audit event —
    creation and the final resolution via `app.hitl.decisions.apply_decision`
    are the audited transitions; this is an intermediate UI-visibility state)."""
    if escalation.state == "open":
        escalation.state = "in_review"
