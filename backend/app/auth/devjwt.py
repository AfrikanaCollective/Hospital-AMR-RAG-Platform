"""Dev JWT provider (ARCH-011). Seeded HS256 issuer; roles embedded in the token.

For local development only. `DEVJWT_SIGNING_KEY` / `DEVJWT_ISSUER` from config.
Phase 4 implements verification; Phase 1 provides the shape.
"""

from __future__ import annotations

from app.auth.provider import AuthContext


class DevJwtProvider:
    def authenticate(self, token: str) -> AuthContext:
        raise NotImplementedError("Phase 4: verify HS256 dev token, extract sub + roles")
