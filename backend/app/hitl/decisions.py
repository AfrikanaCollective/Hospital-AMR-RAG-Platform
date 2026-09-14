"""Accept-axis effects on state (ARCH §13.2; PRD-032).

full_accept / partial_accept / reject / out_of_scope and what each does to:
the shown answer, conversation memory, patient_context, escalation/eval, and
audit. This module is the single place those effects are applied so they
stay consistent with the table in ARCHITECTURE.md §13.2.

`out_of_scope` (DEVIATIONS.md #84) is a reviewer judgment about the
*request*, not the candidate answer — distinct from `reject`, which judges an
attempted answer as wrong/ungrounded/unsafe. Its state effects mirror
`reject`'s (nothing is shown, all provisional patient_context for the result
is rolled back) but its own `resolution` value and `outcome` keep it
separately reportable — mislabeled-scope items are a routing-quality signal,
not a grounding-quality one, and pooling them into `rejected` would blur that
distinction in any evidence report built from `hitl_decision`/`escalation`
rows.

A `result_id` (an `eval.result` row, when this escalation is tied to one — see
`trigger_detail["result_id"]`) drives the patient_context effect. Not every
escalation carries a result (e.g. a plain SCOPE-1 grounding failure has no
patient_context entries to begin with) — when absent, the patient_context
effect is a no-op, which is correct, not a gap.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.audit.log import write_event
from app.crypto.provider import get_crypto
from app.db.models.hitl import Escalation, HitlDecision
from app.hitl.escalation import EscalationNotFoundError
from app.memory.patient_context import (
    accept_all_provisional_for_result,
    partial_accept_for_result,
    rollback_provisional_for_result,
)
from app.schemas.enums import HitlAcceptAction

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Summary of ARCH §13.2 — used by tests and by the implementation.
EFFECTS: dict[str, dict[str, str]] = {
    HitlAcceptAction.FULL_ACCEPT: {
        "shown_answer": "released as-is; marked validated",
        "conversation_memory": "assistant turn committed as accepted",
        "patient_context": "provisional entries -> reviewer_accepted",
        "escalation": "resolution=accepted, state=resolved",
    },
    HitlAcceptAction.PARTIAL_ACCEPT: {
        "shown_answer": "reviewer-edited version canonical; original + diff kept",
        "conversation_memory": (
            "edited turn committed, linked to original; removed spans logged as failures"
        ),
        "patient_context": "only retained entries -> reviewer_edited; rest expired",
        "escalation": "resolution=partial; reason_code required",
    },
    HitlAcceptAction.REJECT: {
        "shown_answer": "not released / retracted; safe fallback shown",
        "conversation_memory": (
            "rejected turn (question kept, body = rejection notice + reason_code)"
        ),
        "patient_context": "ALL provisional entries for this result rolled back (valid_to=now)",
        "escalation": "resolution=rejected; reason_code required; flagged as eval failure",
    },
    HitlAcceptAction.OUT_OF_SCOPE: {
        "shown_answer": "not released; safe out-of-scope notice shown",
        "conversation_memory": (
            "out-of-scope turn (question kept, body = out-of-scope notice + reason_code)"
        ),
        "patient_context": "ALL provisional entries for this result rolled back (valid_to=now)",
        "escalation": (
            "resolution=out_of_scope; reason_code required; flagged as a routing failure "
            "(not a grounding failure)"
        ),
    },
}

_RESOLUTION_BY_ACTION = {
    HitlAcceptAction.FULL_ACCEPT: "accepted",
    HitlAcceptAction.PARTIAL_ACCEPT: "partial",
    HitlAcceptAction.REJECT: "rejected",
    HitlAcceptAction.OUT_OF_SCOPE: "out_of_scope",
}

_AAD_NAMESPACE = b"hitl-decision-edited-answer:"


def apply_decision(
    session: Session,
    *,
    escalation_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    action: HitlAcceptAction,
    edited_answer: str | None = None,
    span_actions: list[dict] | None = None,
    accepted_context_ids: list[str] | None = None,
    reason_code: str | None = None,
) -> HitlDecision:
    escalation = session.get(Escalation, escalation_id)
    if escalation is None:
        raise EscalationNotFoundError(f"no escalation {escalation_id}")

    decision = HitlDecision(
        escalation_id=escalation_id,
        message_id=escalation.message_id,
        reviewer_id=reviewer_id,
        action=action.value,
        span_actions=span_actions,
        accepted_context_ids=accepted_context_ids,
        reason_code=reason_code,
    )
    session.add(decision)
    session.flush()

    if edited_answer is not None:
        crypto = get_crypto()
        decision.edited_answer_enc = crypto.encrypt(
            edited_answer.encode("utf-8"), aad=_AAD_NAMESPACE + str(decision.id).encode("utf-8")
        )

    escalation.state = "resolved"
    escalation.resolution = _RESOLUTION_BY_ACTION[action]
    escalation.resolved_by = reviewer_id
    escalation.resolved_at = datetime.now(UTC)

    result_id_raw = (escalation.trigger_detail or {}).get("result_id")
    result_id = uuid.UUID(result_id_raw) if result_id_raw else None
    if result_id is not None:
        if action == HitlAcceptAction.FULL_ACCEPT:
            accept_all_provisional_for_result(session, result_id)
        elif action == HitlAcceptAction.PARTIAL_ACCEPT:
            accepted_ids = {uuid.UUID(i) for i in (accepted_context_ids or [])}
            partial_accept_for_result(session, result_id, accepted_ids)
        elif action in (HitlAcceptAction.REJECT, HitlAcceptAction.OUT_OF_SCOPE):
            rollback_provisional_for_result(session, result_id)

    write_event(
        session,
        action="hitl_action",
        actor_id=reviewer_id,
        actor_role="reviewer",
        conversation_id=escalation.conversation_id,
        outcome=_RESOLUTION_BY_ACTION[action],
        detail={
            "escalation_id": str(escalation_id),
            "action": action.value,
            "reason_code": reason_code,
        },
    )
    return decision
