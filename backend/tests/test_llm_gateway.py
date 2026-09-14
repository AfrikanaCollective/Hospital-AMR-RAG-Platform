"""LLMGateway.chat() -- HTTP call against the OpenAI-ish gateway contract
(ARCH-005), offline via httpx.MockTransport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.llm.gateway import LLMGateway, LLMGatewayError

_RETRY_ATTEMPTS_BEFORE_SUCCESS = 2


def _settings(**overrides: object) -> Settings:
    base = {
        "model_id": "primary-model",
        "model_id_verified": True,
        "llm_gateway_url": "http://llm-gateway:8080",
        "llm_max_retries": 0,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg, arg-type]


def _gateway_with_transport(settings: Settings, handler) -> LLMGateway:
    gw = LLMGateway(settings=settings)
    gw._client = httpx.Client(
        base_url=settings.llm_gateway_url, transport=httpx.MockTransport(handler)
    )
    return gw


def test_chat_success_returns_text_and_model_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.read())
        assert payload["model"] == "primary-model"
        assert payload["messages"] == [{"role": "user", "content": "hi"}]
        return httpx.Response(
            200,
            json={
                "model": "primary-model",
                "choices": [{"message": {"role": "assistant", "content": "hello back"}}],
                "usage": {"total_tokens": 5},
            },
        )

    gw = _gateway_with_transport(_settings(), handler)
    result = gw.chat(system="", messages=[{"role": "user", "content": "hi"}])
    assert result.text == "hello back"
    assert result.model_id == "primary-model"
    assert result.used_fallback is False
    assert result.usage == {"total_tokens": 5}


def test_chat_sends_bearer_auth_header_when_api_key_set() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200, json={"model": "primary-model", "choices": [{"message": {"content": "x"}}]}
        )

    gw = _gateway_with_transport(_settings(llm_gateway_api_key="secret-token"), handler)
    gw.chat(system="", messages=[])
    assert seen["auth"] == "Bearer secret-token"


def test_chat_falls_back_to_next_model_on_failure() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.read())["model"]
        calls.append(model)
        if model == "primary-model":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(
            200, json={"model": model, "choices": [{"message": {"content": "from fallback"}}]}
        )

    gw = _gateway_with_transport(_settings(model_id_fallbacks="fallback-model"), handler)
    result = gw.chat(system="", messages=[])
    assert result.text == "from fallback"
    assert result.used_fallback is True
    assert calls == ["primary-model", "fallback-model"]


def test_chat_raises_gateway_error_when_all_models_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    gw = _gateway_with_transport(_settings(model_id_fallbacks="fallback-model"), handler)
    with pytest.raises(LLMGatewayError):
        gw.chat(system="", messages=[])


def test_chat_retries_before_falling_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.llm.gateway.time.sleep", lambda _s: None)
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < _RETRY_ATTEMPTS_BEFORE_SUCCESS:
            return httpx.Response(500, json={"error": "transient"})
        return httpx.Response(
            200, json={"model": "primary-model", "choices": [{"message": {"content": "ok"}}]}
        )

    gw = _gateway_with_transport(_settings(llm_max_retries=2), handler)
    result = gw.chat(system="", messages=[])
    assert result.text == "ok"
    assert len(attempts) == _RETRY_ATTEMPTS_BEFORE_SUCCESS


def test_placeholder_model_id_refuses_to_construct() -> None:
    with pytest.raises(RuntimeError):
        LLMGateway(settings=_settings(model_id="<set-me>", model_id_verified=False))
