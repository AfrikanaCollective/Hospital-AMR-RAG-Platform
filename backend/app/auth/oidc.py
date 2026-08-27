"""OIDC provider adapter — STUB (ARCH-011; DEVIATIONS.md #4).

Kept as a drop-in seam so a self-hosted IdP (e.g. Keycloak, `full` compose
profile) can replace the dev JWT provider without touching call sites.
Phase 4+ implements JWKS fetch + token verification + role mapping.
"""

from __future__ import annotations

from app.auth.provider import AuthContext


class OidcProvider:
    def authenticate(self, token: str) -> AuthContext:
        raise NotImplementedError("Deferred: OIDC verification (ARCH-011). Use AUTH_PROVIDER=devjwt.")
