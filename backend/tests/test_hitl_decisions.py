"""Accept-axis effects on state (ARCH §13.2; PRD-032)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.audit.log as audit_log
import app.memory.patient_context as pc
from app.db.models.hitl import Escalation
from app.db.models.memory import PatientContext
from app.hitl.decisions import apply_decision
from app.schemas.enums import HitlAcceptAction

RESULT_ID = uuid.uuid4()
REVIEWER_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, escalation: Escalation) -> None:
        self._escalation = escalation
        self.added: list = []

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return self._escalation if pk == self._escalation.id else None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


def _open_escalation(*, result_id: uuid.UUID | None = RESULT_ID) -> Escalation:
    return Escalation(
        id=uuid.uuid4(),
        trigger_code="weak_support",
        state="open",
        trigger_detail={"result_id": str(result_id)} if result_id else {},
    )


def test_full_accept_marks_all_provisional_accepted(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    rows = [
        PatientContext(
            id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            kind="note",
            payload={},
            result_id=RESULT_ID,
            provenance="model_provisional",
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
        for _ in range(2)
    ]
    monkeypatch.setattr(pc, "_find_provisional_for_result", lambda s, rid: rows)

    escalation = _open_escalation()
    session = _FakeSession(escalation)
    decision = apply_decision(
        session,
        escalation_id=escalation.id,
        reviewer_id=REVIEWER_ID,
        action=HitlAcceptAction.FULL_ACCEPT,
    )
    assert decision.action == "full_accept"
    assert escalation.state == "resolved"
    assert escalation.resolution == "accepted"
    assert all(r.provenance == "reviewer_accepted" for r in rows)


def test_partial_accept_keeps_selected_expires_rest(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    kept = PatientContext(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        kind="note",
        payload={},
        result_id=RESULT_ID,
        provenance="model_provisional",
        valid_from=datetime.now(UTC),
        valid_to=None,
    )
    expired = PatientContext(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        kind="note",
        payload={},
        result_id=RESULT_ID,
        provenance="model_provisional",
        valid_from=datetime.now(UTC),
        valid_to=None,
    )
    monkeypatch.setattr(pc, "_find_provisional_for_result", lambda s, rid: [kept, expired])

    escalation = _open_escalation()
    session = _FakeSession(escalation)
    apply_decision(
        session,
        escalation_id=escalation.id,
        reviewer_id=REVIEWER_ID,
        action=HitlAcceptAction.PARTIAL_ACCEPT,
        edited_answer="edited text",
        accepted_context_ids=[str(kept.id)],
        reason_code="trimmed_unsupported_span",
    )
    assert kept.provenance == "reviewer_edited"
    assert kept.valid_to is None
    assert expired.valid_to is not None
    assert escalation.resolution == "partial"


def test_reject_rolls_back_all_provisional(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    rows = [
        PatientContext(
            id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            kind="note",
            payload={},
            result_id=RESULT_ID,
            provenance="model_provisional",
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
    ]
    monkeypatch.setattr(pc, "_find_provisional_for_result", lambda s, rid: rows)

    escalation = _open_escalation()
    session = _FakeSession(escalation)
    apply_decision(
        session,
        escalation_id=escalation.id,
        reviewer_id=REVIEWER_ID,
        action=HitlAcceptAction.REJECT,
        reason_code="not_grounded",
    )
    assert escalation.resolution == "rejected"
    assert rows[0].valid_to is not None


def test_out_of_scope_rolls_back_all_provisional_and_sets_resolution(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    rows = [
        PatientContext(
            id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            kind="note",
            payload={},
            result_id=RESULT_ID,
            provenance="model_provisional",
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
    ]
    monkeypatch.setattr(pc, "_find_provisional_for_result", lambda s, rid: rows)

    escalation = _open_escalation()
    session = _FakeSession(escalation)
    decision = apply_decision(
        session,
        escalation_id=escalation.id,
        reviewer_id=REVIEWER_ID,
        action=HitlAcceptAction.OUT_OF_SCOPE,
        reason_code="scope_2_3_shaped_request",
    )
    assert decision.action == "out_of_scope"
    assert escalation.resolution == "out_of_scope"
    assert rows[0].valid_to is not None


def test_no_result_id_is_a_patient_context_noop(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    escalation = _open_escalation(result_id=None)
    session = _FakeSession(escalation)
    decision = apply_decision(
        session,
        escalation_id=escalation.id,
        reviewer_id=REVIEWER_ID,
        action=HitlAcceptAction.FULL_ACCEPT,
    )
    assert decision.action == "full_accept"
    assert escalation.resolution == "accepted"
