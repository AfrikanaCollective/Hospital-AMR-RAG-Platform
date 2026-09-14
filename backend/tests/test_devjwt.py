"""Dev JWT provider (ARCH-011)."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.auth.devjwt import DevJwtError, DevJwtProvider, mint_token


def test_mint_then_authenticate_round_trips() -> None:
    token = mint_token(user_id="u1", roles=frozenset({"clinician", "reviewer"}), is_clinician=True)
    ctx = DevJwtProvider().authenticate(token)
    assert ctx.user_id == "u1"
    assert ctx.roles == frozenset({"clinician", "reviewer"})
    assert ctx.is_clinician is True


def test_expired_token_rejected() -> None:
    token = mint_token(
        user_id="u1", roles=frozenset({"admin"}), is_clinician=False, ttl=timedelta(seconds=-1)
    )
    with pytest.raises(DevJwtError):
        DevJwtProvider().authenticate(token)


def test_garbage_token_rejected() -> None:
    with pytest.raises(DevJwtError):
        DevJwtProvider().authenticate("not-a-jwt")


def test_wrong_signing_key_rejected() -> None:
    token = jwt.encode(
        {"sub": "u1", "iss": "hospital-rag-dev", "roles": ["admin"], "is_clinician": False},
        "some-other-key",
        algorithm="HS256",
    )
    with pytest.raises(DevJwtError):
        DevJwtProvider().authenticate(token)


def test_wrong_issuer_rejected() -> None:
    from app.config import get_settings

    token = jwt.encode(
        {"sub": "u1", "roles": ["admin"], "is_clinician": False, "iss": "someone-else"},
        get_settings().devjwt_signing_key,
        algorithm="HS256",
    )
    with pytest.raises(DevJwtError):
        DevJwtProvider().authenticate(token)


def test_missing_required_claim_rejected() -> None:
    from app.config import get_settings

    token = jwt.encode(
        {"iss": get_settings().devjwt_issuer, "roles": ["admin"]},  # no "sub"
        get_settings().devjwt_signing_key,
        algorithm="HS256",
    )
    with pytest.raises(DevJwtError):
        DevJwtProvider().authenticate(token)
