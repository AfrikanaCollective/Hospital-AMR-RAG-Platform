"""Per-patient context repository (ARCH §11, ARCH-024; PRD-024).

Cross-session, structured, NON-diagnostic. Enforces:
- `kind` in the closed set (guideline_match | stage_classification |
  missing_info | note),
- NO recommendation-shaped payloads (no "next_step"/"plan"/"do"/"treat" style
  keys or free-form directive text),
- same ACL as the patient record + audit on read/write,
- no cross-patient reads (there is no API to read across patients),
- supersession via valid_to, never deletion,
- provisional -> reviewer_accepted/edited only via a HITL accept; reject rolls
  provisional entries back.

Write auditing (DEVIATIONS.md #72): reuses `action="record_access"` (the
closest of `AuditEvent.action`'s documented values — `patient_context` isn't
diagnostic PHI in the clinical-notes sense, but it is patient-linked
structured output and gets the same audit treatment) with
`detail={"patient_context_kind": kind, "op": "context_write"}` distinguishing
it from a record field read.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.audit.log import write_event
from app.db.models.memory import PATIENT_CONTEXT_KINDS, PatientContext

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_FORBIDDEN_KEYS = {
    "next_step",
    "next_steps",
    "recommendation",
    "recommended_action",
    "plan",
    "management_plan",
    "should",
    "do_next",
    "treatment_plan",
    "action",
}


class RecommendationShapedWriteError(ValueError):
    """Raised when a patient_context write would constitute a recommendation (ARCH-024)."""


def validate_patient_context_write(kind: str, payload: dict) -> None:
    if kind not in PATIENT_CONTEXT_KINDS:
        raise ValueError(
            f"patient_context.kind must be one of {PATIENT_CONTEXT_KINDS}, got {kind!r}"
        )
    lowered = {str(k).lower() for k in payload}
    bad = lowered & _FORBIDDEN_KEYS
    if bad:
        raise RecommendationShapedWriteError(
            f"patient_context payload contains recommendation-shaped keys {sorted(bad)} (ARCH-024)"
        )


def write_context(
    session: Session,
    *,
    patient_id: uuid.UUID,
    kind: str,
    payload: dict,
    provenance: str = "model_provisional",
    source_message_id: uuid.UUID | None = None,
    result_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    purpose: str | None = None,
) -> PatientContext:
    validate_patient_context_write(kind, payload)
    row = PatientContext(
        patient_id=patient_id,
        kind=kind,
        payload=payload,
        provenance=provenance,
        source_message_id=source_message_id,
        result_id=result_id,
        valid_from=datetime.now(UTC),
        valid_to=None,
        created_by=created_by,
    )
    session.add(row)
    session.flush()
    write_event(
        session,
        action="record_access",
        actor_id=actor_id,
        actor_role=actor_role,
        purpose=purpose,
        patient_id=patient_id,
        detail={"patient_context_kind": kind, "op": "context_write"},
    )
    return row


def _find_provisional_for_result(session: Session, result_id: uuid.UUID) -> list[PatientContext]:
    return list(
        session.execute(
            select(PatientContext).where(
                PatientContext.result_id == result_id,
                PatientContext.provenance == "model_provisional",
                PatientContext.valid_to.is_(None),
            )
        )
        .scalars()
        .all()
    )


def mark_provenance(session: Session, patient_context_id: uuid.UUID, provenance: str) -> None:
    """Accept-axis effect (full_accept / partial_accept): the provisional row
    itself becomes the accepted/edited record — no new row, no supersession
    (ARCH §13.2)."""
    stmt = update(PatientContext).where(PatientContext.id == patient_context_id)
    session.execute(stmt.values(provenance=provenance))


def accept_all_provisional_for_result(session: Session, result_id: uuid.UUID) -> int:
    """full_accept effect: every still-provisional row for this result becomes
    `reviewer_accepted` (ARCH §13.2) — not just an explicitly-selected subset."""
    rows = _find_provisional_for_result(session, result_id)
    for row in rows:
        row.provenance = "reviewer_accepted"
    return len(rows)


def partial_accept_for_result(
    session: Session, result_id: uuid.UUID, accepted_ids: set[uuid.UUID]
) -> None:
    """partial_accept effect: rows in `accepted_ids` become `reviewer_edited`;
    every other still-provisional row for this result is expired (ARCH §13.2)."""
    now = datetime.now(UTC)
    for row in _find_provisional_for_result(session, result_id):
        if row.id in accepted_ids:
            row.provenance = "reviewer_edited"
        else:
            row.valid_to = now


def rollback_provisional_for_result(session: Session, result_id: uuid.UUID) -> int:
    """Reject-axis effect: expire (never delete) every still-provisional
    `patient_context` row tied to this result (ARCH §13.2). Returns the count
    rolled back."""
    rows = _find_provisional_for_result(session, result_id)
    now = datetime.now(UTC)
    for row in rows:
        row.valid_to = now
    return len(rows)
