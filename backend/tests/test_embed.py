"""Embedding backend dispatch (ARCH-004). `local` is dependency-injected in
tests (DEVIATIONS.md #51) — no real model download. `gateway` is exercised
offline via httpx.MockTransport (DEVIATIONS.md #103), matching
tests/test_llm_gateway.py's pattern — no real network call."""

from __future__ import annotations

import json

import httpx
import numpy as np
import pytest

import app.ingestion.embed as embed_mod
from app.config import get_settings
from app.ingestion.embed import embed_texts

_ENCODE_DIM_STUB = 384


def test_stub_backend_returns_normalized_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    get_settings.cache_clear()
    try:
        vecs = embed_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == _ENCODE_DIM_STUB
    finally:
        get_settings.cache_clear()


class _FakeModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(
        self, texts: list[str], *, normalize_embeddings: bool, **_kw: object
    ) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(t)), 0.0] for t in texts]


def test_local_backend_applies_prefix_and_uses_injected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeModel()
    monkeypatch.setattr(embed_mod, "_LOCAL_MODEL_LOADER", lambda model_id: fake)
    embed_mod._get_local_model.cache_clear()
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("EMBEDDING_DOC_PREFIX", "passage: ")
    monkeypatch.setenv("EMBEDDING_QUERY_PREFIX", "query: ")
    get_settings.cache_clear()
    try:
        embed_texts(["chunk text"], is_query=False)
        assert fake.calls[-1] == ["passage: chunk text"]
        embed_texts(["a question"], is_query=True)
        assert fake.calls[-1] == ["query: a question"]
    finally:
        get_settings.cache_clear()
        embed_mod._get_local_model.cache_clear()


class _NumpyModel:
    """Mimics a real `sentence_transformers.SentenceTransformer.encode()`
    return shape: a numpy array of numpy.float32 elements, not native Python
    floats (DEVIATIONS.md #118) — the offline `_FakeModel` above already
    returns native floats and so could never have caught this; found live
    the first time EMBEDDING_BACKEND=local ran against a real model, when
    `EvalQuestion.generator_meta["embedding"] = embedding` failed a plain
    `json.dumps` with `TypeError: Object of type float32 is not JSON
    serializable`."""

    def encode(self, texts: list[str], *, normalize_embeddings: bool, **_kw: object) -> np.ndarray:
        return np.array([[float(len(t)), 0.0] for t in texts], dtype=np.float32)


def test_local_backend_returns_json_serializable_native_floats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(embed_mod, "_LOCAL_MODEL_LOADER", lambda model_id: _NumpyModel())
    embed_mod._get_local_model.cache_clear()
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    get_settings.cache_clear()
    try:
        vecs = embed_texts(["chunk text"])
        assert all(isinstance(x, float) for x in vecs[0])
        json.dumps(vecs)  # must not raise TypeError: Object of type float32 ...
    finally:
        get_settings.cache_clear()
        embed_mod._get_local_model.cache_clear()


def _gateway_with_transport(handler) -> None:
    """Monkeypatch-free helper: point _GATEWAY_CLIENT_BUILDER at a client
    wired to httpx.MockTransport, mirroring tests/test_llm_gateway.py's
    _gateway_with_transport (no real network call)."""
    embed_mod._GATEWAY_CLIENT_BUILDER = lambda url, ca_bundle, timeout: httpx.Client(  # noqa: ARG005
        base_url=url, transport=httpx.MockTransport(handler)
    )
    embed_mod._get_gateway_client.cache_clear()


def test_gateway_backend_posts_model_and_input_returns_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        payload = json.loads(request.read())
        assert payload["model"] == "qllama/bge-large-en-v1.5:latest"
        assert payload["input"] == ["passage: chunk text"]
        return httpx.Response(
            200,
            json={
                "id": "abc",
                "model": "qllama/bge-large-en-v1.5:latest",
                "backend_used": "ollama-primary",
                "embeddings": [[0.1, 0.2, 0.3]],
            },
        )

    _gateway_with_transport(handler)
    monkeypatch.setenv("EMBEDDING_BACKEND", "gateway")
    monkeypatch.setenv("EMBEDDING_MODEL_ID", "qllama/bge-large-en-v1.5:latest")
    monkeypatch.setenv("EMBEDDING_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("EMBEDDING_DOC_PREFIX", "passage: ")
    get_settings.cache_clear()
    try:
        vecs = embed_texts(["chunk text"], is_query=False)
        assert vecs == [[0.1, 0.2, 0.3]]
    finally:
        get_settings.cache_clear()
        embed_mod._GATEWAY_CLIENT_BUILDER = embed_mod._build_gateway_client
        embed_mod._get_gateway_client.cache_clear()


def test_gateway_backend_sends_bearer_auth_when_api_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"model": "m", "embeddings": [[1.0]]})

    _gateway_with_transport(handler)
    monkeypatch.setenv("EMBEDDING_BACKEND", "gateway")
    monkeypatch.setenv("EMBEDDING_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("EMBEDDING_GATEWAY_API_KEY", "secret-token")
    get_settings.cache_clear()
    try:
        embed_texts(["x"])
        assert seen["auth"] == "Bearer secret-token"
    finally:
        get_settings.cache_clear()
        embed_mod._GATEWAY_CLIENT_BUILDER = embed_mod._build_gateway_client
        embed_mod._get_gateway_client.cache_clear()


def test_gateway_backend_sends_sni_hostname_extension_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEVIATIONS.md #103: same SNI/hostname-verification override as
    LLMGateway, for reaching a self-hosted embedding gateway via
    host.docker.internal against a cert issued for "localhost"."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["sni_hostname"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, json={"model": "m", "embeddings": [[1.0]]})

    _gateway_with_transport(handler)
    monkeypatch.setenv("EMBEDDING_BACKEND", "gateway")
    monkeypatch.setenv("EMBEDDING_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("EMBEDDING_GATEWAY_SNI_HOSTNAME", "localhost")
    get_settings.cache_clear()
    try:
        embed_texts(["x"])
        assert seen["sni_hostname"] == "localhost"
    finally:
        get_settings.cache_clear()
        embed_mod._GATEWAY_CLIENT_BUILDER = embed_mod._build_gateway_client
        embed_mod._get_gateway_client.cache_clear()
