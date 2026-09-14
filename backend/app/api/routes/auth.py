"""Dev-JWT login (ARCH-011; PRD-086).

POST /auth/dev-login   body: {"email": "..."} -> a signed dev JWT for a
seeded demo user (`scripts/seed_db.py` / `make seed`).

**Not a real authentication flow — dev/CI only.** There is no password: this
mints a token for whoever's email matches a seeded `iam.user` row, embedding
their real seeded roles. It is unconditionally unavailable
(`404 Not Found`, the route "doesn't exist") whenever `AUTH_PROVIDER` is not
`devjwt` — a real deployment sets `AUTH_PROVIDER=oidc` and this endpoint
disappears rather than needing to be separately disabled/firewalled.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.audit.log import write_event
from app.auth.devjwt import mint_token
from app.auth.repository import find_user_with_roles
from app.config import get_settings
from app.schemas.auth import DevLoginRequest, DevLoginResponse

router = APIRouter()


@router.post("/dev-login", response_model=DevLoginResponse)
async def dev_login(body: DevLoginRequest, session: Session = Depends(get_db)) -> DevLoginResponse:
    settings = get_settings()
    if settings.auth_provider != "devjwt":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    found = find_user_with_roles(session, body.email)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no seeded user {body.email!r} (run `make seed`)"
        )
    user, roles = found

    token = mint_token(user_id=str(user.id), roles=roles, is_clinician=user.is_clinician)
    write_event(
        session,
        action="login",
        actor_id=user.id,
        actor_role=sorted(roles)[0] if roles else None,
        outcome="issued",
        detail={"provider": "devjwt", "roles": sorted(roles)},
    )
    return DevLoginResponse(access_token=token, user_id=str(user.id), roles=sorted(roles))
