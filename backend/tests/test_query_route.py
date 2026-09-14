"""`POST /query` HTTP route (PRD-011..PRD-016; ARCH-016).

Offline via FastAPI's TestClient: `get_db` is dependency-overridden with a
fake session (`app.memory.conversation.append_message`/`create_conversation`
only ever call `.add`/`.flush`); `app.api.routes.query._GRAPH_INVOKE_FN` is
monkeypatched so no real compiled graph (and therefore no real DB/Qdrant/LLM
gateway/Postgres checkpointer) is needed — the graph's own routing is already
covered end-to-end by `test_agent_graph.py`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.routes.query as query_mod
from app.api.deps import Principal, current_principal, get_db
from app.main import app as fastapi_app
from app.schemas.enums import EscalationTrigger, ObservedOutcome, ScopeLabel, SegmentType


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@pytest.fixture(autouse=True)
def _overrides():
    session = _FakeSession()
    fastapi_app.dependency_overrides[get_db] = lambda: session
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="dev-user", roles=frozenset({"clinician"}), is_clinician=True
    )
    yield session
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_released_answer_round_trips(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    def _fake_invoke(initial_state, thread_id):  # noqa: ANN001, ARG001
        return {
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "retrieval": [{"chunk_id": "ch1", "score": 0.9}],
            "grounding_report": {"action": "release"},
            "final_answer": {
                "segments": [
                    {"type": SegmentType.FRAMING, "text": "Per the retrieved guideline:"},
                    {
                        "type": SegmentType.CLAIM,
                        "text": "Guideline X recommends recording respiratory rate.",
                        "citation_ids": ["c1"],
                    },
                ],
                "citations": [
                    {
                        "citation_id": "c1",
                        "document_id": "d1",
                        "document_title": "Guideline X",
                        "document_version_id": "v1",
                        "version_label": "2021",
                        "chunk_id": "ch1",
                        "page_start": 1,
                        "page_end": 1,
                        "char_start": 0,
                        "char_end": 10,
                        "quote": "recommends recording respiratory rate",
                        "quote_char_start": 0,
                        "quote_char_end": 10,
                    }
                ],
            },
        }

    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", _fake_invoke)
    resp = client.post(
        "/api/query",
        json={"question": "What does the guideline say about fever?"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed_outcome"] == "well_supported"
    assert body["scope_label"] == "scope_1"
    assert len(body["segments"]) == 2
    assert len(body["citations"]) == 1
    assert body["disclaimer"]
    assert body["escalation"] is None


def test_escalated_response_round_trips(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    def _fake_invoke(initial_state, thread_id):  # noqa: ANN001, ARG001
        return {
            "scope_label": ScopeLabel.SCOPE_2_EXCLUDED,
            "escalation": {
                "trigger_code": EscalationTrigger.SCOPE_BOUNDARY,
                "message": "Routed to clinician review.",
                "escalation_id": str(uuid.uuid4()),
            },
        }

    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", _fake_invoke)
    resp = client.post(
        "/api/query",
        json={
            "question": "What should I do next for this patient?",
            "patient_id": str(uuid.uuid4()),
        },
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["observed_outcome"] == "escalated"
    assert body["escalation"]["trigger_code"] == "scope_boundary"
    assert body["segments"] == []
    assert body["citations"] == []


def test_missing_purpose_header_is_rejected(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", lambda *a, **k: {})  # noqa: ARG005
    resp = client.post("/api/query", json={"question": "x"})
    assert resp.status_code == 400


def test_pipeline_exception_returns_502_not_a_partial_answer(
    client: TestClient, monkeypatch
) -> None:  # noqa: ANN001
    def _boom(initial_state, thread_id):  # noqa: ANN001, ARG001
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", _boom)
    resp = client.post(
        "/api/query", json={"question": "x"}, headers={"X-Purpose-Of-Use": "clinical_care"}
    )
    assert resp.status_code == 502
