"""`/conversations/*` HTTP routes (ARCH-017; PRD-022, PRD-NG-011)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Principal, current_principal, get_db
from app.main import app as fastapi_app


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self._by_id: dict = {}

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            self._by_id[obj.id] = obj

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return self._by_id.get(pk)


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


def test_create_conversation(client: TestClient) -> None:
    resp = client.post("/api/conversations", json={})
    assert resp.status_code == 201
    assert resp.json()["status"] == "active"


def test_get_unknown_conversation_404(client: TestClient) -> None:
    resp = client.get(f"/api/conversations/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_conversation_after_create(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    create_resp = client.post("/api/conversations", json={})
    conversation_id = create_resp.json()["id"]

    import app.memory.conversation as conv_mod

    monkeypatch.setattr(conv_mod, "_list_messages", lambda s, cid: [])  # noqa: ARG005
    resp = client.get(f"/api/conversations/{conversation_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == conversation_id
    assert resp.json()["messages"] == []


def test_handoff_is_not_implemented_stub(client: TestClient) -> None:
    resp = client.post(f"/api/conversations/{uuid.uuid4()}/handoff")
    assert resp.status_code == 501
