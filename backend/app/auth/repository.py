"""Read access to `iam.user`/`iam.user_role` for the dev-login flow (ARCH-011).

The only DB-touching piece of the auth stack — kept separate from
`app.auth.devjwt` (pure token logic, no DB) so the token mint/verify path has
no database dependency at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import select

from app.db.models.iam import User, UserRole

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


class UserWithRoles(NamedTuple):
    user: User
    roles: frozenset[str]


def find_user_with_roles(session: Session, email: str) -> UserWithRoles | None:
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        return None
    return UserWithRoles(user, _roles_for_user(session, user.id))


def _roles_for_user(session: Session, user_id: uuid.UUID) -> frozenset[str]:
    stmt = select(UserRole.role_code).where(UserRole.user_id == user_id)
    return frozenset(session.execute(stmt).scalars().all())
