"""`/hitl/*` HTTP routes (PRD-030, PRD-032, PRD-033; ARCH §12, §13).

Offline via FastAPI's TestClient: `get_db` and `current_principal` are
dependency-overridden. `app.hitl.escalation.get_escalation` /
`app.hitl.decisions.apply_decision`'s own DB reads are exercised against a
fake session carrying a real, in-memory `Escalation` row — no real Postgres.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

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
    assert body["state"] == "open"


def test_get_unknown_escalation_404(client: TestClient) -> None:
    resp = client.get(f"/api/hitl/escalations/{uuid.uuid4()}")
    assert resp.status_code == 404


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
