"""Dev-login request/response models (ARCH-011)."""

from __future__ import annotations

from pydantic import BaseModel


class DevLoginRequest(BaseModel):
    email: str


class DevLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    roles: list[str]
