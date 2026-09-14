"""`iam.user`/`user_role` lookup for dev-login (ARCH-011)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.auth.repository import find_user_with_roles
from app.db.models.iam import User, UserRole

USER_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, user: User | None, roles: list[UserRole]) -> None:
        self._user = user
        self._roles = roles

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
        return _Res([r.role_code for r in self._roles])


def test_found_user_returns_roles() -> None:
    user = User(
        id=USER_ID,
        email="reviewer1@example.dev",
        display_name="Demo Reviewer One",
        is_clinician=True,
        created_at=datetime.now(UTC),
    )
    roles = [
        UserRole(user_id=USER_ID, role_code="clinician"),
        UserRole(user_id=USER_ID, role_code="reviewer"),
    ]
    session = _FakeSession(user, roles)
    found = find_user_with_roles(session, "reviewer1@example.dev")
    assert found is not None
    assert found.user.id == USER_ID
    assert found.roles == frozenset({"clinician", "reviewer"})


def test_unknown_email_returns_none() -> None:
    session = _FakeSession(None, [])
    assert find_user_with_roles(session, "nobody@example.dev") is None
