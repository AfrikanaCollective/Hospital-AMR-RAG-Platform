"""`/hitl/*` HTTP routes (PRD-030, PRD-032, PRD-033; ARCH §12, §13).

Offline via FastAPI's TestClient: `get_db` and `current_principal` are
dependency-overridden. `app.hitl.escalation.get_escalation` /
`app.hitl.decisions.apply_decision`'s own DB reads are exercised against a
fake session carrying a real, in-memory `Escalation` row — no real Postgres.
`GET /hitl/escalations` (list) monkeypatches `app.hitl.escalation.list_escalations`
directly instead — its own real (DB-facing) behavior is covered by
`tests/test_hitl_escalation.py`; here only the route's wiring/serialization/
role-gating is exercised.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.api.routes.hitl as hitl_mod
import app.audit.log as audit_log
from app.api.deps import Principal, current_principal, get_db
from app.crypto.provider import get_crypto
from app.db.models.hitl import Escalation
from app.main import app as fastapi_app

ESCALATION_ID = uuid.uuid4()


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


@pytest.fixture
def escalation() -> Escalation:
    crypto = get_crypto()
    esc = Escalation(
        id=ESCALATION_ID,
        trigger_code="low_confidence",
        state="open",
        trigger_detail={},
        candidate_answer_enc=crypto.encrypt(
            b"draft answer text", aad=b"escalation-candidate-answer:" + str(ESCALATION_ID).encode()
        ),
        created_at=datetime.now(UTC),
    )
    return esc


@pytest.fixture(autouse=True)
def _overrides(escalation: Escalation, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)  # noqa: ARG005
    session = _FakeSession(escalation)
    fastapi_app.dependency_overrides[get_db] = lambda: session
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="reviewer-1", roles=frozenset({"reviewer"}), is_clinician=True
    )
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_get_escalation_decrypts_candidate_answer(client: TestClient) -> None:
    resp = client.get(f"/api/hitl/escalations/{ESCALATION_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate_answer"] == "draft answer text"


def test_get_escalation_by_reviewer_transitions_to_in_review(
    client: TestClient,
    escalation: Escalation,  # noqa: ANN001
) -> None:
    """ARCH §12.2: "open -> (reviewer pulls) in_review". Opening the detail
    view IS the pull — not itself an audited transition (creation and the
    final resolution are; see `mark_in_review`'s own docstring)."""
    assert escalation.state == "open"
    resp = client.get(f"/api/hitl/escalations/{ESCALATION_ID}")
    assert resp.status_code == 200
    assert resp.json()["state"] == "in_review"
    assert escalation.state == "in_review"


def test_get_escalation_by_admin_does_not_transition(
    client: TestClient,
    escalation: Escalation,  # noqa: ANN001
) -> None:
    """Only a reviewer "pulling" an item counts as the ARCH §12.2 transition
    — an admin merely inspecting one shouldn't silently take it out of the
    open pool for other reviewers."""
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="admin-1", roles=frozenset({"admin"}), is_clinician=False
    )
    resp = client.get(f"/api/hitl/escalations/{ESCALATION_ID}")
    assert resp.status_code == 200
    assert resp.json()["state"] == "open"
    assert escalation.state == "open"


def test_get_unknown_escalation_404(client: TestClient) -> None:
    resp = client.get(f"/api/hitl/escalations/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_list_escalations_serializes_rows(
    client: TestClient,
    escalation: Escalation,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(hitl_mod, "list_escalations", lambda session, **kw: [escalation])  # noqa: ARG005
    resp = client.get("/api/hitl/escalations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(escalation.id)
    assert body[0]["trigger_code"] == "low_confidence"
    assert body[0]["state"] == "open"


def test_list_escalations_threads_state_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    def _fake_list(session, **kwargs):  # noqa: ANN001, ARG001
        captured.update(kwargs)
        return []

    monkeypatch.setattr(hitl_mod, "list_escalations", _fake_list)
    resp = client.get("/api/hitl/escalations", params={"state": "resolved"})
    assert resp.status_code == 200
    assert resp.json() == []
    assert captured["state"] == "resolved"


def test_list_escalations_requires_reviewer_or_admin(client: TestClient) -> None:
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="clinician-1", roles=frozenset({"clinician"}), is_clinician=True
    )
    resp = client.get("/api/hitl/escalations")
    assert resp.status_code == 403


def test_full_accept_decision(client: TestClient, escalation: Escalation) -> None:  # noqa: ANN001
    resp = client.post(
        f"/api/hitl/escalations/{ESCALATION_ID}/decision", json={"action": "full_accept"}
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "full_accept"
    assert escalation.state == "resolved"
    assert escalation.resolution == "accepted"


def test_reject_requires_reason_code(client: TestClient) -> None:
    resp = client.post(f"/api/hitl/escalations/{ESCALATION_ID}/decision", json={"action": "reject"})
    assert resp.status_code == 422


def test_reject_with_reason_code(client: TestClient, escalation: Escalation) -> None:  # noqa: ANN001
    resp = client.post(
        f"/api/hitl/escalations/{ESCALATION_ID}/decision",
        json={"action": "reject", "reason_code": "not_grounded"},
    )
    assert resp.status_code == 200
    assert escalation.resolution == "rejected"


def test_out_of_scope_requires_reason_code(client: TestClient) -> None:
    resp = client.post(
        f"/api/hitl/escalations/{ESCALATION_ID}/decision", json={"action": "out_of_scope"}
    )
    assert resp.status_code == 422


def test_out_of_scope_with_reason_code(client: TestClient, escalation: Escalation) -> None:  # noqa: ANN001
    resp = client.post(
        f"/api/hitl/escalations/{ESCALATION_ID}/decision",
        json={"action": "out_of_scope", "reason_code": "scope_2_3_shaped_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "out_of_scope"
    assert escalation.resolution == "out_of_scope"


def test_partial_accept_succeeds_without_edited_answer(
    client: TestClient, escalation: Escalation
) -> None:
    """DEVIATIONS.md #101: neither the ranker nor a reviewer resolving an
    escalation directly is required to write an edited answer —
    `accepted_context_ids` alone is a complete, valid `partial_accept`. A
    reason code is still required here (unchanged, DEVIATIONS #100 only
    relaxed the *rank-mode* reason-code requirement, not this workflow's)."""
    resp = client.post(
        f"/api/hitl/escalations/{ESCALATION_ID}/decision",
        json={"action": "partial_accept", "reason_code": "trimmed_unsupported_span"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "partial_accept"
    assert escalation.resolution == "partial"
