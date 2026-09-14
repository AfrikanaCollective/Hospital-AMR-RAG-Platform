"""`POST /auth/dev-login` (ARCH-011)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.audit.log as audit_log
from app.api.deps import get_db
from app.db.models.iam import User
from app.main import app as fastapi_app

USER_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, user: User | None) -> None:
        self._user = user
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def execute(self, stmt: object) -> object:
        entity = stmt.column_descriptions[0]["entity"]  # type: ignore[attr-defined]

        class _Res:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalar_one_or_none(self) -> object:
                return self._rows[0] if self._rows else None

            def scalars(self) -> _Res:
                return self

            def all(self) -> list:
                return self._rows

        if entity is User:
            return _Res([self._user] if self._user else [])
        return _Res(["clinician", "reviewer"] if self._user else [])


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture(autouse=True)
def _no_real_audit_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)


def test_dev_login_success(client: TestClient) -> None:
    user = User(
        id=USER_ID,
        email="reviewer1@example.dev",
        display_name="Demo Reviewer One",
        is_clinician=True,
        created_at=datetime.now(UTC),
    )
    fastapi_app.dependency_overrides[get_db] = lambda: _FakeSession(user)
    try:
        resp = client.post("/api/auth/dev-login", json={"email": "reviewer1@example.dev"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == str(USER_ID)
        assert set(body["roles"]) == {"clinician", "reviewer"}
        assert body["token_type"] == "bearer"
        assert body["access_token"]

        from app.auth.devjwt import DevJwtProvider

        ctx = DevJwtProvider().authenticate(body["access_token"])
        assert ctx.user_id == str(USER_ID)
        assert ctx.roles == frozenset({"clinician", "reviewer"})
    finally:
        fastapi_app.dependency_overrides.clear()


def test_dev_login_unknown_email_404(client: TestClient) -> None:
    fastapi_app.dependency_overrides[get_db] = lambda: _FakeSession(None)
    try:
        resp = client.post("/api/auth/dev-login", json={"email": "nobody@example.dev"})
        assert resp.status_code == 404
    finally:
        fastapi_app.dependency_overrides.clear()


def test_dev_login_unavailable_when_not_devjwt_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.routes.auth as auth_routes
    from app.config import Settings

    monkeypatch.setattr(
        auth_routes, "get_settings", lambda: Settings(_env_file=None, auth_provider="oidc")
    )
    resp = client.post("/api/auth/dev-login", json={"email": "reviewer1@example.dev"})
    assert resp.status_code == 404
