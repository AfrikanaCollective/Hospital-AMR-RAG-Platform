"""Constraint #6 — no hardcoded model; placeholder blocks the answer path (PRD-101)."""

from __future__ import annotations

import pytest

from app.config import PLACEHOLDER_MODEL_ID, Settings


def _s(**over: object) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def test_placeholder_is_detected() -> None:
    assert _s(model_id=PLACEHOLDER_MODEL_ID).is_model_placeholder()
    assert _s(model_id="").is_model_placeholder()
    assert not _s(model_id="some-gateway-model").is_model_placeholder()


def test_answer_path_refuses_placeholder() -> None:
    with pytest.raises(RuntimeError):
        _s(model_id=PLACEHOLDER_MODEL_ID).validate_model_config(require_answer_path=True)


def test_answer_path_allows_real_id() -> None:
    _s(model_id="gw-model-x", model_id_verified=True).validate_model_config(
        require_answer_path=True
    )


def test_startup_does_not_raise_on_placeholder() -> None:
    # startup only warns; it must not crash the service
    _s(model_id=PLACEHOLDER_MODEL_ID).validate_model_config(require_answer_path=False)


def test_no_model_name_literals_in_gateway_source() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "llm" / "gateway.py"
    text = src.read_text()
    # the gateway must not hardcode a model id
    for banned in ("gpt-", "claude-", "llama-", "mistral-", "gemini-"):
        assert banned not in text.lower()


def test_gateway_transport_warns_on_plaintext_external_host(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _s(llm_gateway_url="http://gateway.example.com:8080").validate_gateway_transport()
    assert any("https" in r.message for r in caplog.records)


def test_gateway_transport_silent_for_known_internal_hosts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _s(llm_gateway_url="http://llm-gateway:8080").validate_gateway_transport()
    assert caplog.records == []


def test_gateway_transport_silent_for_https(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _s(llm_gateway_url="https://gateway.example.com").validate_gateway_transport()
    assert caplog.records == []
