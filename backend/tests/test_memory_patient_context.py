"""Per-patient context repository — persistence half (ARCH §11, ARCH-024).

`validate_patient_context_write` itself is already covered by
`test_patient_context_rejects_recommendations.py` (gating test, CLAUDE.md §5);
this file covers write_context / mark_provenance / rollback_provisional_for_result.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.audit.log as audit_log
import app.memory.patient_context as pc
from app.db.models.memory import PatientContext

PATIENT_ID = uuid.uuid4()
RESULT_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, execute_result: list | None = None) -> None:
        self.added: list = []
        self._execute_result = execute_result or []
        self.executed: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def execute(self, stmt: object) -> object:
        self.executed.append(stmt)

        class _Result:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Result:
                return self

            def all(self) -> list:
                return self._rows

        return _Result(self._execute_result)


def test_write_context_persists_and_audits(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    row = pc.write_context(
        session,
        patient_id=PATIENT_ID,
        kind="stage_classification",
        payload={"stage": "stabilisation", "confidence": 0.9},
        result_id=RESULT_ID,
    )
    assert row.kind == "stage_classification"
    assert row.provenance == "model_provisional"
    assert row.valid_to is None
    # write_context + write_event both call session.add
    assert row in session.added
    audit_events = [o for o in session.added if hasattr(o, "action")]
    assert audit_events[0].action == "record_access"
    assert audit_events[0].detail == {
        "patient_context_kind": "stage_classification",
        "op": "context_write",
    }


def test_write_context_rejects_recommendation_shaped_payload() -> None:
    import pytest

    with pytest.raises(pc.RecommendationShapedWriteError):
        pc.write_context(
            _FakeSession(), patient_id=PATIENT_ID, kind="note", payload={"next_step": "x"}
        )


def test_rollback_provisional_for_result_expires_rows() -> None:
    rows = [
        PatientContext(
            id=uuid.uuid4(),
            patient_id=PATIENT_ID,
            kind="note",
            payload={},
            result_id=RESULT_ID,
            provenance="model_provisional",
            valid_from=datetime.now(UTC),
            valid_to=None,
        )
        for _ in range(2)
    ]
    session = _FakeSession(execute_result=rows)
    count = pc.rollback_provisional_for_result(session, RESULT_ID)
    assert count == 2
    assert all(r.valid_to is not None for r in rows)


def test_mark_provenance_issues_update(monkeypatch) -> None:  # noqa: ANN001
    session = _FakeSession()
    pc.mark_provenance(session, uuid.uuid4(), "reviewer_accepted")
    assert len(session.executed) == 1
