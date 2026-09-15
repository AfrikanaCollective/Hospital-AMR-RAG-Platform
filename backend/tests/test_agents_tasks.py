"""`app.agents.tasks.run_query` — the async `/query` Celery task (ARCH-007,
PRD-105; DEVIATIONS.md #94)."""

from __future__ import annotations

import uuid

import pytest

import app.agents.tasks as tasks_mod
import app.audit.log as audit_log
from app.schemas.enums import ObservedOutcome, ScopeLabel, SegmentType

CONVERSATION_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass


def test_run_query_invokes_graph_persists_and_returns_response_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    monkeypatch.setattr(
        tasks_mod,
        "session_scope",
        lambda: _session_scope_cm(session),
    )

    captured_state = {}

    def _fake_invoke(initial_state, thread_id):  # noqa: ANN001
        captured_state["initial_state"] = initial_state
        captured_state["thread_id"] = thread_id
        return {
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "model_id": "stub-model-v1",
            "grounding_report": {"action": "release"},
            "final_answer": {
                "segments": [{"type": SegmentType.FRAMING, "text": "Per the guideline:"}],
                "citations": [],
            },
        }

    monkeypatch.setattr(tasks_mod, "_INVOKE_GRAPH_FN", _fake_invoke)

    initial_state = {
        "conversation_id": CONVERSATION_ID,
        "user_id": USER_ID,
        "purpose": "clinical_care",
        "roles": ["clinician"],
        "query": "What does the guideline say?",
    }
    result = tasks_mod.run_query(initial_state)

    # thread_id is per-turn, not per-conversation (DEVIATIONS.md #105) — a
    # fresh id every call, conversation_id kept only as a readable prefix.
    assert captured_state["thread_id"] != CONVERSATION_ID
    assert captured_state["thread_id"].startswith(f"{CONVERSATION_ID}:")
    assert result["conversation_id"] == CONVERSATION_ID
    assert result["observed_outcome"] == "well_supported"
    assert result["scope_label"] == "scope_1"
    assert len(result["segments"]) == 1

    answer_events = [obj for obj in session.added if getattr(obj, "action", None) == "answer"]
    assert len(answer_events) == 1
    assert answer_events[0].model_id == "stub-model-v1"


def _session_scope_cm(session):  # noqa: ANN001, ANN202
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        yield session

    return _cm()
