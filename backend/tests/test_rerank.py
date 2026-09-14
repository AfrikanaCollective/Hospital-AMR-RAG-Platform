"""Reranker backend dispatch (ARCH-012). `local` is dependency-injected in
tests (DEVIATIONS.md #51) -- no real model download."""

from __future__ import annotations

import pytest

import app.retrieval.rerank as rerank_mod
from app.config import get_settings
from app.retrieval.rerank import rerank


def test_stub_backend_scores_by_lexical_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANKER_BACKEND", "stub")
    get_settings.cache_clear()
    try:
        scores = rerank("blood cultures", ["blood cultures before antibiotics", "unrelated text"])
        assert scores[0] > scores[1]
    finally:
        get_settings.cache_clear()


class _FakeCrossEncoder:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, str]]] = []

    def predict(self, pairs: list[tuple[str, str]], *, batch_size: int) -> list[float]:
        self.calls.append(pairs)
        return [1.0 if q in p else 0.0 for q, p in pairs]


def test_local_backend_uses_injected_model_and_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(
        rerank_mod, "_LOCAL_MODEL_LOADER", lambda model_id, *, device, max_length: fake
    )
    rerank_mod._get_local_model.cache_clear()
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    monkeypatch.setenv("RERANKER_BATCH_SIZE", "4")
    get_settings.cache_clear()
    try:
        scores = rerank("sepsis", ["neonatal sepsis management", "unrelated passage"])
        assert scores == [1.0, 0.0]
        expected_calls = [("sepsis", "neonatal sepsis management"), ("sepsis", "unrelated passage")]
        assert fake.calls[0] == expected_calls
    finally:
        get_settings.cache_clear()
        rerank_mod._get_local_model.cache_clear()


def test_local_backend_empty_passages_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    get_settings.cache_clear()
    try:
        assert rerank("q", []) == []
    finally:
        get_settings.cache_clear()


def test_gateway_backend_not_yet_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERANKER_BACKEND", "gateway")
    get_settings.cache_clear()
    try:
        with pytest.raises(NotImplementedError):
            rerank("q", ["p"])
    finally:
        get_settings.cache_clear()
