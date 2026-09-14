"""Missing-info agent (SCOPE-2.2; ARCH §9.2; DEVIATIONS.md #76)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import app.agents.missing_info_agent as mia
from app.schemas.enums import EscalationTrigger

PATIENT_ID = str(uuid.uuid4())

_SNAPSHOT = {
    "confidence": {
        "top_score": 0.9,
        "supporting_count": 1,
        "low_confidence": False,
        "essentially_empty": False,
    }
}


@contextmanager
def _fake_session_scope():
    yield None


def _criteria_chunk(chunk_id: str, criteria: list[dict]) -> dict:
    return {"chunk_id": chunk_id, "chunk_type": "criteria", "meta": {"criteria": criteria}}


def test_no_patient_attached_escalates() -> None:
    out = mia.run({"query": "what is missing?"})  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.PHI_AMBIGUITY


def test_missing_field_reported_with_citation_and_no_escalation(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mia, "_SESSION_SCOPE", _fake_session_scope)
    chunk = _criteria_chunk(
        "c1", [{"field": "gestational age", "operator": "<", "value": 34.0, "unit": "weeks"}]
    )
    monkeypatch.setattr(mia, "_RETRIEVE_FN", lambda query, **kw: ([chunk], _SNAPSHOT))  # noqa: ARG005
    monkeypatch.setattr(mia, "_FIELD_INDEX_FN", lambda session, pid: {})  # noqa: ARG005

    out = mia.run({"query": "what is missing?", "patient_id": PATIENT_ID})  # type: ignore[arg-type]
    assert out["missing_info"] == [
        {
            "field": "encounter.gestational_age_weeks",
            "why": "required by the criterion 'gestational age' < 34.0",
            "citation_id": "c1",
        }
    ]
    # SCOPE-2.2 is clarification-seeking, not a HITL hold (DEVIATIONS.md #76).
    assert "escalation" not in out
    assert out["retrieval"] == [chunk]
    assert out["retrieval_confidence"]["low_confidence"] is False


def test_present_field_is_not_reported_missing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(mia, "_SESSION_SCOPE", _fake_session_scope)
    chunk = _criteria_chunk(
        "c1", [{"field": "heart rate", "operator": ">", "value": 160.0, "unit": None}]
    )
    monkeypatch.setattr(mia, "_RETRIEVE_FN", lambda query, **kw: ([chunk], _SNAPSHOT))  # noqa: ARG005
    monkeypatch.setattr(
        mia,
        "_FIELD_INDEX_FN",
        lambda session, pid: {"vitals.0.heart_rate_bpm": True},  # noqa: ARG005
    )

    out = mia.run({"query": "what is missing?", "patient_id": PATIENT_ID})  # type: ignore[arg-type]
    assert out["missing_info"] == []
    assert "escalation" not in out
