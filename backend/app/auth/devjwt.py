"""Dev JWT provider (ARCH-011). Seeded HS256 issuer; roles embedded in the token.

For local development / CI only. `DEVJWT_SIGNING_KEY` / `DEVJWT_ISSUER` from
config. `mint_token` exists so `POST /auth/dev-login` (`app.api.routes.auth`)
can issue a token for a seeded demo user (`scripts/seed_db.py`) — there is no
password; this is explicitly not a real authentication flow (ARCH-011: "prod:
OIDC adapter"). Both the mint and verify paths use the same HS256 key/issuer,
so a token only verifies within the deployment that minted it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from app.auth.provider import AuthContext
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

ALGORITHM = "HS256"
_DEFAULT_TTL = timedelta(hours=8)
_PLACEHOLDER_SIGNING_KEY = "dev-only-change-me-32-bytes-minimum!!"


def _warn_if_placeholder_key(key: str) -> None:
    if key == _PLACEHOLDER_SIGNING_KEY:
        logger.warning(
            "DEVJWT_SIGNING_KEY is the placeholder default. DEV KEY — not for real "
            "data. Set a real random secret before this deployment is reachable "
            "outside a local dev/CI loop."
        )


class DevJwtError(ValueError):
    """Raised on a missing/invalid/expired dev JWT."""


def mint_token(
    *, user_id: str, roles: frozenset[str], is_clinician: bool, ttl: timedelta = _DEFAULT_TTL
) -> str:
    settings = get_settings()
    _warn_if_placeholder_key(settings.devjwt_signing_key)
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iss": settings.devjwt_issuer,
        "roles": sorted(roles),
        "is_clinician": is_clinician,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.devjwt_signing_key, algorithm=ALGORITHM)


class DevJwtProvider:
    def authenticate(self, token: str) -> AuthContext:
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.devjwt_signing_key,
                algorithms=[ALGORITHM],
                issuer=settings.devjwt_issuer,
                options={"require": ["sub", "roles", "exp", "iat"]},
            )
        except jwt.InvalidTokenError as exc:
            raise DevJwtError(f"invalid dev JWT: {exc}") from exc
        return AuthContext(
            user_id=payload["sub"],
            roles=frozenset(payload.get("roles") or []),
            is_clinician=bool(payload.get("is_clinician", False)),
        )
