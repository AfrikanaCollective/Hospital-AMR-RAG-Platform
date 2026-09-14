"""Shared FastAPI dependencies (ARCH-034; PRD-084, PRD-086).

- `get_db` — SQLAlchemy session, with the RLS session GUC set from the caller's
  patient scope.
- `current_principal` — authenticated user + roles (via `AuthProvider`).
- `require_role(...)` — RBAC guard for a route.
- `purpose_of_use` — required query/header attribute for patient-scoped calls;
  recorded in every audit row.

`current_principal` (Phase 4) requires a real `Authorization: Bearer <token>`
header, verified via `app.auth.provider.get_auth_provider()` (dev: HS256 JWT;
prod: OIDC, stub). There is no more permissive dev fallback — a request with
no/invalid token is `401`. Tests hit routes exclusively via
`app.dependency_overrides[current_principal] = ...` (established throughout
this suite since Phase 2/3), so this tightening doesn't touch them; only
`GET /healthz` and OpenAPI schema introspection are ever exercised without an
override, and neither depends on `current_principal`.

`get_db` (`app.db.session.session_scope`) commits on a clean request, rolls
back on an exception; the RLS GUC it can set (`patient_scope`) is wired at the
specific call sites that hold a single authoritative `patient_id`
(`app.records.access`, `app.memory.patient_context` callers), not generically
here — `POST /query`'s `patient_id` lives in the request body, which isn't
resolved yet when `get_db` itself runs as a dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.provider import get_auth_provider
from app.db.session import session_scope

# DEVIATIONS.md #75: the Phase-1 dev-auth fallback issues a bare string
# user_id ("dev-user"), but several Phase-3 tables (memory.conversation.user_id,
# hitl_decision.reviewer_id, ...) are UUID columns. `principal_uuid` derives a
# stable UUID from a non-UUID principal id; once Phase 4 issues real UUID
# principals, `uuid.UUID(principal.user_id)` succeeds directly and this
# fallback is never reached.
_PRINCIPAL_UUID_NAMESPACE = uuid.UUID("6a3b6b0e-6e2b-4b8a-9a8b-2b7e7c9b6a11")


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    is_clinician: bool = False


def principal_uuid(principal: Principal) -> uuid.UUID:
    try:
        return uuid.UUID(principal.user_id)
    except ValueError:
        return uuid.uuid5(_PRINCIPAL_UUID_NAMESPACE, principal.user_id)


def get_db() -> Iterator[Session]:
    """Yield a DB session for one request: commits if the request handler
    completes without raising, rolls back otherwise (`session_scope`).
    `patient_scope` (the RLS GUC) is not yet threaded from the caller's
    principal — Phase 4 (ARCH-034)."""
    with session_scope() as session:
        yield session


_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    """Resolve the caller from `Authorization: Bearer <token>` via the
    configured `AuthProvider` (ARCH-011, ARCH-034)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers=_WWW_AUTHENTICATE
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        ctx = get_auth_provider().authenticate(token)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid or expired token", headers=_WWW_AUTHENTICATE
        ) from exc
    return Principal(user_id=ctx.user_id, roles=ctx.roles, is_clinician=ctx.is_clinician)


def require_role(*allowed: str):
    def _guard(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.roles.intersection(allowed):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires one of: {allowed}")
        return principal

    return _guard


def purpose_of_use(x_purpose_of_use: str | None = Header(default=None)) -> str:
    """Required for patient-scoped routes (ARCH-034). Recorded in audit."""
    if not x_purpose_of_use:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Purpose-Of-Use header required")
    return x_purpose_of_use
