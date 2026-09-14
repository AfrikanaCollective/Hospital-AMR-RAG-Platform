"""`/admin/*` HTTP routes (PRD-086; ARCH-034, ARCH-035).

Offline via FastAPI's TestClient: `get_db`/`current_principal` dependency-
overridden (a fake session; an admin principal). `app.audit.log.query_events`/
`verify_chain` are monkeypatched on the route module so no real Postgres is
needed — their own real behavior is covered by `tests/test_audit_append_only.py`
and a real-Postgres verification pass (DEVIATIONS.md #93).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin as admin_mod
from app.api.deps import Principal, current_principal, get_db
from app.db.models.audit import AuditEvent
from app.main import app as fastapi_app


class _FakeSession:
    pass


def _event(**overrides) -> AuditEvent:  # noqa: ANN003
    defaults = dict(
        id=1,
        ts=datetime.now(UTC),
        actor_id=uuid.uuid4(),
        actor_role="clinician",
        purpose="clinical_care",
        action="query",
        conversation_id=None,
        patient_id=None,
        query_hash="a" * 64,
        retrieved=None,
        record_fields=None,
        model_id=None,
        response_hash=None,
        grounding_summary=None,
        outcome=None,
        detail=None,
        prev_hash="0" * 64,
        row_hash="b" * 64,
    )
    defaults.update(overrides)
    return AuditEvent(**defaults)


@pytest.fixture
def admin_client():
    def _fake_get_db():
        yield _FakeSession()

    def _admin_principal() -> Principal:
        return Principal(user_id=str(uuid.uuid4()), roles=frozenset({"admin"}), is_clinician=False)

    fastapi_app.dependency_overrides[get_db] = _fake_get_db
    fastapi_app.dependency_overrides[current_principal] = _admin_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def non_admin_client():
    def _fake_get_db():
        yield _FakeSession()

    def _clinician_principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()), roles=frozenset({"clinician"}), is_clinician=True
        )

    fastapi_app.dependency_overrides[get_db] = _fake_get_db
    fastapi_app.dependency_overrides[current_principal] = _clinician_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


def test_config_summary_requires_admin(non_admin_client: TestClient) -> None:
    resp = non_admin_client.get("/api/admin/config")
    assert resp.status_code == 403


def test_config_summary_returns_non_secret_fields(admin_client: TestClient) -> None:
    resp = admin_client.get("/api/admin/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "secrets_backend" in body
    assert "auth_provider" in body


def test_audit_requires_admin(non_admin_client: TestClient) -> None:
    resp = non_admin_client.get("/api/admin/audit")
    assert resp.status_code == 403


def test_audit_returns_serialized_events(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [_event(id=2, action="answer"), _event(id=1, action="query")]
    monkeypatch.setattr(admin_mod, "query_events", lambda session, **kw: events)  # noqa: ARG005
    resp = admin_client.get("/api/admin/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["id"] for e in body["events"]] == [2, 1]
    assert body["events"][0]["action"] == "answer"
    assert "broken_chain_ids" not in body
    # never leaks raw ciphertext columns
    assert "query_text_enc" not in body["events"][0]
    assert "response_text_enc" not in body["events"][0]


def test_audit_threads_filters(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _fake_query_events(session, **kwargs):  # noqa: ANN001, ARG001
        captured.update(kwargs)
        return []

    monkeypatch.setattr(admin_mod, "query_events", _fake_query_events)
    pid = str(uuid.uuid4())
    resp = admin_client.get(
        "/api/admin/audit", params={"action": "login", "patient_id": pid, "limit": 10}
    )
    assert resp.status_code == 200, resp.text
    assert captured["action"] == "login"
    assert str(captured["patient_id"]) == pid
    assert captured["limit"] == 10


def test_audit_verify_includes_broken_chain_ids(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin_mod, "query_events", lambda session, **kw: [])  # noqa: ARG005
    monkeypatch.setattr(admin_mod, "verify_chain", lambda session: [3, 7])
    resp = admin_client.get("/api/admin/audit", params={"verify": "true"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["broken_chain_ids"] == [3, 7]
