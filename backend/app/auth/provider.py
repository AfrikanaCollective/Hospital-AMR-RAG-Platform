"""AuthProvider interface + selection (ARCH-011).

AUTH_PROVIDER = devjwt (seeded signed JWT, roles embedded) | oidc (adapter stub).
Reviewers must additionally be clinicians (iam.user.is_clinician).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    roles: frozenset[str]
    is_clinician: bool


class AuthProvider(Protocol):
    def authenticate(self, token: str) -> AuthContext: ...


def get_auth_provider() -> AuthProvider:
    # Deferred (not both providers' deps need to be present in every
    # deployment; only the configured one is ever imported).
    name = get_settings().auth_provider
    if name == "devjwt":
        from app.auth.devjwt import DevJwtProvider  # noqa: PLC0415

        return DevJwtProvider()
    if name == "oidc":
        from app.auth.oidc import OidcProvider  # noqa: PLC0415

        return OidcProvider()
    raise ValueError(f"unknown AUTH_PROVIDER: {name!r}")
