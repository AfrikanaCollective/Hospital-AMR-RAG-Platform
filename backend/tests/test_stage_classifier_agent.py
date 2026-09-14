"""Stage-classifier agent (SCOPE-2.1; ARCH §9.2)."""

from __future__ import annotations

from contextlib import contextmanager

import app.agents.stage_classifier_agent as sca
from app.schemas.enums import EscalationTrigger


@contextmanager
def _fake_session_scope():
    yield None


def _criteria_chunk(chunk_id: str, heading: str, criteria: list[dict]) -> dict:
    return {
        "chunk_id": chunk_id,
        "chunk_type": "criteria",
        "heading": heading,
        "meta": {"criteria": criteria},
    }


_SNAPSHOT = {
    "confidence": {
        "top_score": 0.9,
        "supporting_count": 1,
        "low_confidence": False,
        "essentially_empty": False,
    }
}


def test_single_passing_stage_is_classified(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(sca, "_SESSION_SCOPE", _fake_session_scope)
    chunk = _criteria_chunk(
        "c1",
        "Criteria for Stabilisation Phase",
        [{"field": "heart rate", "operator": ">", "value": 160.0, "unit": None}],
    )
    monkeypatch.setattr(sca, "_RETRIEVE_FN", lambda query, **kw: ([chunk], _SNAPSHOT))  # noqa: ARG005

    state = {
        "query": "what stage is this patient in?",
        "patient_features": {"vitals.heart_rate_bpm": 180.0},
    }
    out = sca.run(state)  # type: ignore[arg-type]
    assert out["stage_classification"]["stage"] == "Criteria for Stabilisation Phase"
    assert out["stage_classification"]["uncertain"] is False
    assert "escalation" not in out


def test_no_passing_stage_escalates_uncertain(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(sca, "_SESSION_SCOPE", _fake_session_scope)
    chunk = _criteria_chunk(
        "c1",
        "Criteria for Stabilisation Phase",
        [{"field": "heart rate", "operator": ">", "value": 220.0, "unit": None}],
    )
    monkeypatch.setattr(sca, "_RETRIEVE_FN", lambda query, **kw: ([chunk], _SNAPSHOT))  # noqa: ARG005

    state = {"query": "stage?", "patient_features": {"vitals.heart_rate_bpm": 180.0}}
    out = sca.run(state)  # type: ignore[arg-type]
    assert out["stage_classification"]["uncertain"] is True
    assert out["escalation"]["trigger_code"] == EscalationTrigger.STAGE_CLASSIFICATION_UNCERTAIN


def test_multiple_passing_stages_escalates_uncertain(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(sca, "_SESSION_SCOPE", _fake_session_scope)
    chunk1 = _criteria_chunk(
        "c1", "Stage A", [{"field": "heart rate", "operator": ">", "value": 100.0, "unit": None}]
    )
    chunk2 = _criteria_chunk(
        "c2", "Stage B", [{"field": "heart rate", "operator": ">", "value": 120.0, "unit": None}]
    )
    monkeypatch.setattr(sca, "_RETRIEVE_FN", lambda query, **kw: ([chunk1, chunk2], _SNAPSHOT))  # noqa: ARG005

    state = {"query": "stage?", "patient_features": {"vitals.heart_rate_bpm": 180.0}}
    out = sca.run(state)  # type: ignore[arg-type]
    assert out["stage_classification"]["uncertain"] is True


def test_no_criteria_chunks_retrieved_is_uncertain(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(sca, "_SESSION_SCOPE", _fake_session_scope)
    monkeypatch.setattr(sca, "_RETRIEVE_FN", lambda query, **kw: ([], _SNAPSHOT))  # noqa: ARG005
    out = sca.run({"query": "stage?", "patient_features": {}})  # type: ignore[arg-type]
    assert out["stage_classification"]["uncertain"] is True
