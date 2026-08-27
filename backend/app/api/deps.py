"""Shared FastAPI dependencies (ARCH-034; PRD-084, PRD-086).

- `get_db` — SQLAlchemy session, with the RLS session GUC set from the caller's
  patient scope.
- `current_principal` — authenticated user + roles (via `AuthProvider`).
- `require_role(...)` — RBAC guard for a route.
- `purpose_of_use` — required query/header attribute for patient-scoped calls;
  recorded in every audit row.

Phase 1: signatures + a permissive dev fallback so the app boots. Phase 4
implements real enforcement.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    is_clinician: bool = False


def get_db() -> Iterator[object]:
    """Yield a DB session. Phase 2 wires app.db.session.SessionLocal + RLS GUC."""
    raise NotImplementedError("Phase 2: database session wiring (ARCH-008, ARCH-034)")


def current_principal() -> Principal:
    """Resolve the caller via app.auth.provider.AuthProvider. Phase 4."""
    # Dev-only permissive fallback keeps the skeleton importable/bootable.
    return Principal(user_id="dev-user", roles=frozenset({"clinician"}), is_clinician=True)


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
