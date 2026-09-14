"""`POST /query` HTTP route (PRD-011..PRD-016; ARCH-016, ARCH-035).

Offline via FastAPI's TestClient: `app.api.routes.query._SESSION_SCOPE` is
monkeypatched to yield a fake session (`app.memory.conversation.append_message`/
`create_conversation` only ever call `.add`/`.flush`) — NOT `get_db`, which
this route deliberately doesn't use (DEVIATIONS.md #95: it would hold one
request-scoped transaction open across the whole graph invocation). Both of
the route's two separate `with _SESSION_SCOPE() as session:` blocks yield the
SAME fake session object here (one instance, reused), matching how a real
Postgres-backed `session_scope()` call would actually give each block a
*different* real session/transaction — the tests only care that state written
in the first block (the user's turn, the `query` audit event) is still
readable/assertable after the second, which a single shared fake achieves
more simply than modeling two real connections. `app.api.routes.query._GRAPH_INVOKE_FN`
is monkeypatched so no real compiled graph (and therefore no real DB/Qdrant/
LLM gateway/Postgres checkpointer) is needed — the graph's own routing is
already covered end-to-end by `test_agent_graph.py`. `current_principal` is
overridden with a `clinician` principal since the route requires that role
(`require_role`) — `test_query_requires_clinician_role` overrides it with a
non-clinician role to exercise the 403 path instead.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import app.api.routes.query as query_mod
import app.audit.log as audit_log
from app.api.deps import Principal, current_principal
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
def _overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)  # noqa: ARG005
    session = _FakeSession()

    @contextmanager
    def _fake_session_scope():
        yield session

    monkeypatch.setattr(query_mod, "_SESSION_SCOPE", _fake_session_scope)
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


def test_query_requires_clinician_role(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", lambda *a, **k: {})  # noqa: ARG005
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="dev-user", roles=frozenset({"reviewer"}), is_clinician=False
    )
    resp = client.post(
        "/api/query", json={"question": "x"}, headers={"X-Purpose-Of-Use": "clinical_care"}
    )
    assert resp.status_code == 403


def test_query_and_answer_audit_events_written(
    client: TestClient,
    monkeypatch,
    _overrides,  # noqa: ANN001
) -> None:
    def _fake_invoke(initial_state, thread_id):  # noqa: ANN001, ARG001
        return {
            "scope_label": ScopeLabel.SCOPE_1,
            "observed_outcome": ObservedOutcome.WELL_SUPPORTED,
            "model_id": "stub-model-v1",
            "grounding_report": {"action": "release"},
            "final_answer": {
                "segments": [
                    {"type": SegmentType.FRAMING, "text": "Per the retrieved guideline:"},
                ],
                "citations": [],
            },
        }

    monkeypatch.setattr(query_mod, "_GRAPH_INVOKE_FN", _fake_invoke)
    resp = client.post(
        "/api/query",
        json={"question": "What does the guideline say about fever?"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 200

    audit_events = [
        obj for obj in _overrides.added if getattr(obj, "action", None) in ("query", "answer")
    ]
    actions = [e.action for e in audit_events]
    assert actions == ["query", "answer"]

    query_event = audit_events[0]
    assert query_event.purpose == "clinical_care"
    assert query_event.query_hash is not None

    answer_event = audit_events[1]
    assert answer_event.model_id == "stub-model-v1"
    assert answer_event.outcome == "well_supported"
    assert answer_event.grounding_summary == {"action": "release"}
    assert answer_event.response_hash is not None


def test_escalated_answer_audit_event_has_no_response_hash(
    client: TestClient,
    monkeypatch,
    _overrides,  # noqa: ANN001
) -> None:
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
        json={"question": "What should I do next?", "patient_id": str(uuid.uuid4())},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 200

    answer_event = next(obj for obj in _overrides.added if getattr(obj, "action", None) == "answer")
    assert answer_event.outcome == "escalated"
    assert answer_event.response_hash is None
    assert answer_event.model_id is None


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


# ── POST /query/async, GET /query/jobs/{job_id} (DEVIATIONS.md #94) ─────────


class _FakeAsyncResult:
    def __init__(self, id_: str) -> None:
        self.id = id_


def test_submit_query_async_enqueues_and_returns_job_handle(
    client: TestClient,
    monkeypatch,
    _overrides,  # noqa: ANN001
) -> None:
    captured = {}

    def _fake_delay(initial_state):  # noqa: ANN001
        captured["initial_state"] = initial_state
        return _FakeAsyncResult("job-123")

    monkeypatch.setattr(query_mod.run_query, "delay", _fake_delay)
    resp = client.post(
        "/api/query/async",
        json={"question": "What does the guideline say about fever?"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "job-123"
    assert body["status"] == "pending"
    assert body["conversation_id"]
    assert captured["initial_state"]["query"] == "What does the guideline say about fever?"
    assert captured["initial_state"]["conversation_id"] == body["conversation_id"]

    # the user's turn + `query` audit event are written synchronously, same as the sync route
    query_events = [obj for obj in _overrides.added if getattr(obj, "action", None) == "query"]
    assert len(query_events) == 1


def test_submit_query_async_requires_clinician_role(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="dev-user", roles=frozenset({"reviewer"}), is_clinician=False
    )
    resp = client.post(
        "/api/query/async", json={"question": "x"}, headers={"X-Purpose-Of-Use": "clinical_care"}
    )
    assert resp.status_code == 403


def test_query_job_pending(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    class _Pending:
        def ready(self) -> bool:
            return False

    monkeypatch.setattr(query_mod, "_ASYNC_RESULT_FN", lambda job_id: _Pending())  # noqa: ARG005
    resp = client.get("/api/query/jobs/some-job-id")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "job_id": "some-job-id",
        "status": "pending",
        "result": None,
        "error": None,
    }


def test_query_job_done_returns_result(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    result_payload = {
        "conversation_id": str(uuid.uuid4()),
        "message_id": str(uuid.uuid4()),
        "observed_outcome": "well_supported",
        "scope_label": "scope_1",
        "segments": [],
        "citations": [],
        "escalation": None,
    }

    class _Done:
        def ready(self) -> bool:
            return True

        def failed(self) -> bool:
            return False

        result = result_payload

    monkeypatch.setattr(query_mod, "_ASYNC_RESULT_FN", lambda job_id: _Done())  # noqa: ARG005
    resp = client.get("/api/query/jobs/some-job-id")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["result"]["observed_outcome"] == "well_supported"


def test_query_job_failed_returns_error(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    class _Failed:
        def ready(self) -> bool:
            return True

        def failed(self) -> bool:
            return True

        result = RuntimeError("qdrant unreachable")

    monkeypatch.setattr(query_mod, "_ASYNC_RESULT_FN", lambda job_id: _Failed())  # noqa: ARG005
    resp = client.get("/api/query/jobs/some-job-id")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert "qdrant unreachable" in body["error"]
