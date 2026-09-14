"""Patient-record agent (ARCH §10.2; PRD-021, PRD-084)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import app.agents.patient_record_agent as pra
from app.records.access import PatientNotFoundError
from app.schemas.enums import EscalationTrigger

PATIENT_ID = str(uuid.uuid4())


@contextmanager
def _fake_session_scope():
    yield None


def test_no_patient_attached_escalates_phi_ambiguity() -> None:
    out = pra.run({"query": "x"})  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.PHI_AMBIGUITY


def test_fetches_only_requested_fields(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(pra, "_SESSION_SCOPE", _fake_session_scope)
    captured = {}

    def _fake_get_fields(session, patient_id, paths, **kwargs):  # noqa: ANN001, ARG001
        captured["paths"] = paths
        return {p: 1 for p in paths}

    monkeypatch.setattr(pra, "_GET_FIELDS_FN", _fake_get_fields)
    monkeypatch.setattr(pra, "_LIST_FIELDS_FN", lambda session, pid: ["a", "b"])  # noqa: ARG005

    state = {
        "query": "x",
        "patient_id": PATIENT_ID,
        "required_field_paths": ["vitals.heart_rate_bpm"],
        "purpose": "clinical_care",
    }
    out = pra.run(state)  # type: ignore[arg-type]
    assert captured["paths"] == ["vitals.heart_rate_bpm"]
    assert out["patient_features"] == {"vitals.heart_rate_bpm": 1}


def test_falls_back_to_all_available_fields_when_none_required(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(pra, "_SESSION_SCOPE", _fake_session_scope)
    monkeypatch.setattr(pra, "_LIST_FIELDS_FN", lambda session, pid: ["a", "b"])  # noqa: ARG005
    monkeypatch.setattr(
        pra,
        "_GET_FIELDS_FN",
        lambda session, patient_id, paths, **kwargs: dict.fromkeys(paths, 1),  # noqa: ARG005
    )
    state = {"query": "x", "patient_id": PATIENT_ID}
    out = pra.run(state)  # type: ignore[arg-type]
    assert out["patient_features"] == {"a": 1, "b": 1}


def test_missing_patient_record_escalates(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(pra, "_SESSION_SCOPE", _fake_session_scope)
    monkeypatch.setattr(pra, "_LIST_FIELDS_FN", lambda session, pid: [])  # noqa: ARG005

    def _raise(*args, **kwargs):  # noqa: ANN001, ARG001
        raise PatientNotFoundError("no record")

    monkeypatch.setattr(pra, "_GET_FIELDS_FN", _raise)
    out = pra.run({"query": "x", "patient_id": PATIENT_ID})  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.PHI_AMBIGUITY
