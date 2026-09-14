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

Two entry points share the same `_apply_patient_context_effect`/
`_create_hitl_decision` machinery, per ARCH §13.2's "applies to a candidate
answer (held by an escalation, OR a released answer under review_sampling,
OR a live turn a reviewer opens)" — the accept axis is not exclusively an
escalation-resolution concept (DEVIATIONS.md #99):

- `apply_decision` — resolving a `hitl.escalation` directly
  (`POST /hitl/escalations/{id}/decision`): mutates the escalation's own
  state/resolution; derives `result_id` indirectly from
  `escalation.trigger_detail["result_id"]` (not every escalation has one).
- `apply_rating_accept_action` — the accept-axis half of a rank-mode rating
  round (`POST /rubric/results/{id}/ratings`, ARCH §13.2 "Both axes
  together"): every rated result gets one, `result_id` is already known
  directly (no escalation involved, and typically none exists — most rated
  results reach the open queue via `review_sampling` or auto-generation, not
  an escalation).

A `result_id` drives the patient_context effect either way. Not every
escalation carries one (e.g. a plain SCOPE-1 grounding failure has no
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
        "shown_answer": (
            "if edited text was given, that version is canonical (original + diff kept); "
            "otherwise the original stands as-is — an edited answer is optional either way "
            "(DEVIATIONS.md #101), only the accepted-context split is required"
        ),
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


def _apply_patient_context_effect(
    session: Session,
    *,
    action: HitlAcceptAction,
    result_id: uuid.UUID | None,
    accepted_context_ids: list[str] | None,
) -> None:
    if result_id is None:
        return
    if action == HitlAcceptAction.FULL_ACCEPT:
        accept_all_provisional_for_result(session, result_id)
    elif action == HitlAcceptAction.PARTIAL_ACCEPT:
        accepted_ids = {uuid.UUID(i) for i in (accepted_context_ids or [])}
        partial_accept_for_result(session, result_id, accepted_ids)
    elif action in (HitlAcceptAction.REJECT, HitlAcceptAction.OUT_OF_SCOPE):
        rollback_provisional_for_result(session, result_id)


def _create_hitl_decision(
    session: Session,
    *,
    escalation_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
    reviewer_id: uuid.UUID,
    action: HitlAcceptAction,
    edited_answer: str | None,
    span_actions: list[dict] | None,
    accepted_context_ids: list[str] | None,
    reason_code: str | None,
) -> HitlDecision:
    decision = HitlDecision(
        escalation_id=escalation_id,
        message_id=message_id,
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
    return decision


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
    """Resolve a `hitl.escalation` directly."""
    escalation = session.get(Escalation, escalation_id)
    if escalation is None:
        raise EscalationNotFoundError(f"no escalation {escalation_id}")

    decision = _create_hitl_decision(
        session,
        escalation_id=escalation_id,
        message_id=escalation.message_id,
        reviewer_id=reviewer_id,
        action=action,
        edited_answer=edited_answer,
        span_actions=span_actions,
        accepted_context_ids=accepted_context_ids,
        reason_code=reason_code,
    )

    escalation.state = "resolved"
    escalation.resolution = _RESOLUTION_BY_ACTION[action]
    escalation.resolved_by = reviewer_id
    escalation.resolved_at = datetime.now(UTC)

    result_id_raw = (escalation.trigger_detail or {}).get("result_id")
    result_id = uuid.UUID(result_id_raw) if result_id_raw else None
    _apply_patient_context_effect(
        session, action=action, result_id=result_id, accepted_context_ids=accepted_context_ids
    )

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


def apply_rating_accept_action(
    session: Session,
    *,
    result_id: uuid.UUID,
    message_id: uuid.UUID | None,
    reviewer_id: uuid.UUID,
    action: HitlAcceptAction,
    edited_answer: str | None = None,
    accepted_context_ids: list[str] | None = None,
    reason_code: str | None = None,
) -> HitlDecision:
    """The accept-axis half of a rank-mode rating round (ARCH §13.2 "Both axes
    together") — not tied to any `hitl.escalation` (`escalation_id=None`);
    the caller (`app.rubric.workflow.submit_rating`) already resolved
    `result_id`/`message_id` and is responsible for linking the returned
    decision's id back onto its own `RatingRound.accept_action_id`."""
    decision = _create_hitl_decision(
        session,
        escalation_id=None,
        message_id=message_id,
        reviewer_id=reviewer_id,
        action=action,
        edited_answer=edited_answer,
        span_actions=None,
        accepted_context_ids=accepted_context_ids,
        reason_code=reason_code,
    )

    _apply_patient_context_effect(
        session, action=action, result_id=result_id, accepted_context_ids=accepted_context_ids
    )

    write_event(
        session,
        action="hitl_action",
        actor_id=reviewer_id,
        actor_role="reviewer",
        outcome=_RESOLUTION_BY_ACTION[action],
        detail={
            "result_id": str(result_id),
            "action": action.value,
            "reason_code": reason_code,
            "context": "rating_round",
        },
    )
    return decision
