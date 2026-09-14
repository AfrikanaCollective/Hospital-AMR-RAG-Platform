"""Eval harness runner (ARCH §16; PRD-072, PRD-073)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.db.models.eval import EvalQuestion
from app.eval import harness
from app.schemas.enums import EscalationTrigger, ObservedOutcome, ScopeLabel


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


def _question(**overrides) -> EvalQuestion:  # noqa: ANN003
    defaults = {
        "id": uuid.uuid4(),
        "text": "What does the guideline recommend for fever?",
        "provenance": "auto_generated",
        "expected_outcome": "well_supported",
        "in_fixed_testset": True,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return EvalQuestion(**defaults)


@pytest.fixture(autouse=True)
def _session_scope(monkeypatch: pytest.MonkeyPatch):
    from contextlib import contextmanager

    session = _FakeSession()

    @contextmanager
    def _scope():
        yield session

    monkeypatch.setattr(harness, "session_scope", _scope)
    return session


def test_well_supported_question_passes(monkeypatch: pytest.MonkeyPatch, _session_scope) -> None:  # noqa: ANN001
    q = _question()
    monkeypatch.setattr(harness, "_FETCH_FIXED_TESTSET_FN", lambda s: [q])  # noqa: ARG005
    monkeypatch.setattr(
        harness,
        "_INVOKE_PIPELINE_FN",
        lambda text, pid: {  # noqa: ARG005
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "retrieval": [{"chunk_id": "ch1"}],
            "final_answer": {
                "segments": [],
                "citations": [],
                "disclaimer": harness.DISCLAIMER_TEXT,
            },
        },
    )
    report = harness.run_harness()
    assert report.passed is True
    assert report.expected_outcome_pass["well_supported"]["pass_rate"] == 1.0
    assert report.scope_safety["scope_boundary_violations"] == 0


def test_no_guideline_expected_but_answered_fails_gate(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    q = _question(expected_outcome="no_guideline_expected")
    monkeypatch.setattr(harness, "_FETCH_FIXED_TESTSET_FN", lambda s: [q])  # noqa: ARG005
    monkeypatch.setattr(
        harness,
        "_INVOKE_PIPELINE_FN",
        lambda text, pid: {  # noqa: ARG005
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "retrieval": [],
            "final_answer": {
                "segments": [],
                "citations": [],
                "disclaimer": harness.DISCLAIMER_TEXT,
            },
        },
    )
    with pytest.raises(harness.EvalGateFailure):
        harness.run_harness()


def test_no_guideline_expected_and_no_guideline_observed_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # noqa: ANN001
    q = _question(expected_outcome="no_guideline_expected")
    monkeypatch.setattr(harness, "_FETCH_FIXED_TESTSET_FN", lambda s: [q])  # noqa: ARG005
    monkeypatch.setattr(
        harness,
        "_INVOKE_PIPELINE_FN",
        lambda text, pid: {  # noqa: ARG005
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.NO_GUIDELINE,
            "retrieval": [],
            "final_answer": {
                "segments": [],
                "citations": [],
                "disclaimer": harness.DISCLAIMER_TEXT,
            },
        },
    )
    report = harness.run_harness()
    assert report.passed is True
    assert report.scope_safety["no_guideline_expected_pass_rate"] == 1.0


def test_scope_boundary_violation_fails_gate(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    q = _question()
    monkeypatch.setattr(harness, "_FETCH_FIXED_TESTSET_FN", lambda s: [q])  # noqa: ARG005
    monkeypatch.setattr(
        harness,
        "_INVOKE_PIPELINE_FN",
        lambda text, pid: {  # noqa: ARG005
            "scope_label": ScopeLabel.SCOPE_2_EXCLUDED,
            "escalation": {"trigger_code": EscalationTrigger.SCOPE_BOUNDARY, "message": "x"},
        },
    )
    with pytest.raises(harness.EvalGateFailure):
        harness.run_harness()


def test_no_fail_flag_returns_report_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    q = _question(expected_outcome="no_guideline_expected")
    monkeypatch.setattr(harness, "_FETCH_FIXED_TESTSET_FN", lambda s: [q])  # noqa: ARG005
    monkeypatch.setattr(
        harness,
        "_INVOKE_PIPELINE_FN",
        lambda text, pid: {  # noqa: ARG005
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "retrieval": [],
            "final_answer": {
                "segments": [],
                "citations": [],
                "disclaimer": harness.DISCLAIMER_TEXT,
            },
        },
    )
    report = harness.run_harness(fail_on_threshold_breach=False)
    assert report.passed is False
