"""Escalation lifecycle (ARCH §12.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.audit.log as audit_log
from app.db.models.hitl import Escalation
from app.hitl.escalation import create_escalation, list_escalations, mark_in_review


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


class _FakeQuerySession:
    """`list_escalations` builds a real `select(...)` and calls `.execute()`
    directly. This fake ignores the compiled WHERE clause (matching this
    suite's established pattern, e.g. `app.ingestion.corpus_access`'s tests)
    and returns canned rows — the filter itself is a single, standard
    SQLAlchemy `.where()` equality/inequality, the same idiom already used
    (and not separately real-Postgres-verified) elsewhere in this module."""

    def __init__(self, rows: list[Escalation]) -> None:
        self._rows = rows

    def execute(self, stmt: object) -> object:
        class _Res:
            def __init__(self, rows: list[Escalation]) -> None:
                self._rows = rows

            def scalars(self) -> _Res:
                return self

            def all(self) -> list[Escalation]:
                return self._rows

        return _Res(self._rows)


def test_create_escalation_persists_and_audits(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    escalation = create_escalation(
        session,
        trigger_code="low_confidence",
        trigger_detail={"top_score": 0.1},
        candidate_answer="draft text",
    )
    assert escalation.state == "open"
    assert escalation.trigger_code == "low_confidence"
    assert escalation.candidate_answer_enc is not None
    audit_events = [o for o in session.added if hasattr(o, "action")]
    assert audit_events[0].action == "hitl_action"
    assert audit_events[0].outcome == "escalated"


def test_mark_in_review_transitions_from_open() -> None:
    from app.db.models.hitl import Escalation

    escalation = Escalation(id=uuid.uuid4(), trigger_code="low_confidence", state="open")
    mark_in_review(escalation)
    assert escalation.state == "in_review"


def test_mark_in_review_is_noop_once_resolved() -> None:
    from app.db.models.hitl import Escalation

    escalation = Escalation(id=uuid.uuid4(), trigger_code="low_confidence", state="resolved")
    mark_in_review(escalation)
    assert escalation.state == "resolved"


def test_list_escalations_returns_rows() -> None:
    rows = [
        Escalation(
            id=uuid.uuid4(),
            trigger_code="low_confidence",
            state="open",
            created_at=datetime.now(UTC),
        )
    ]
    result = list_escalations(_FakeQuerySession(rows))
    assert result == rows


def test_list_escalations_accepts_explicit_state_filter() -> None:
    """Just confirms the call doesn't crash when a filter is given — the
    fake doesn't evaluate the WHERE clause, see `_FakeQuerySession`."""
    result = list_escalations(_FakeQuerySession([]), state="resolved")
    assert result == []
