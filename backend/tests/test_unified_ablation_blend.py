"""Brute-force score blending for Level 3's dense-bearing arms (PRD-112)."""

from __future__ import annotations

import numpy as np
import pytest

from app.config import get_settings
from app.eval.unified_ablation.blend import (
    blend_bm25_dense,
    bm25_raw_scores,
    combine_dense_scores,
    cosine_raw_scores,
)
from app.retrieval.vectorstore import QdrantVectorStore
from tests.test_hybrid_retrieve import _seed_chunk

_DENSE_DIM = 384


@pytest.fixture(autouse=True)
def _stub_backends(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("RERANKER_BACKEND", "stub")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="unified_ablation_blend_test")
    s.ensure_collection(dense_dim=_DENSE_DIM)
    return s


def test_bm25_raw_scores_favors_the_lexically_matching_chunk(store: QdrantVectorStore) -> None:
    _seed_chunk(store, 1, chunk_id="c1", text="Blood cultures are recommended before antibiotics.")
    _seed_chunk(store, 2, chunk_id="c2", text="zzz completely unrelated zzz")

    scores = bm25_raw_scores(store, "blood cultures antibiotics", ["c1", "c2"])
    assert "c1" in scores
    assert scores.get("c1", 0.0) > scores.get("c2", 0.0)


def test_cosine_raw_scores_ranks_by_similarity_and_returns_every_chunk() -> None:
    chunk_ids = ["near", "far", "mid"]
    matrix = np.array([[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])
    scores = cosine_raw_scores([1.0, 0.0], matrix, chunk_ids)
    assert set(scores) == {"near", "far", "mid"}
    assert scores["near"] > scores["mid"] > scores["far"]


def test_cosine_raw_scores_handles_zero_query_vector_without_crashing() -> None:
    scores = cosine_raw_scores([0.0, 0.0], np.array([[1.0, 0.0], [0.0, 1.0]]), ["a", "b"])
    assert scores["a"] == pytest.approx(0.0)
    assert scores["b"] == pytest.approx(0.0)


def test_combine_dense_scores_is_the_mean_of_two_normalized_channels() -> None:
    a = {"x": 0.0, "y": 10.0}  # normalizes to {x: 0.0, y: 1.0}
    b = {"x": 5.0, "y": 5.0}  # ties -> normalizes to {x: 1.0, y: 1.0}
    combined = combine_dense_scores(a, b)
    assert combined["x"] == pytest.approx((0.0 + 1.0) / 2)
    assert combined["y"] == pytest.approx((1.0 + 1.0) / 2)


def test_combine_dense_scores_fills_a_chunk_missing_from_one_channel_with_zero() -> None:
    a = {"x": 1.0}
    b = {"y": 1.0}
    combined = combine_dense_scores(a, b)
    assert set(combined) == {"x", "y"}


def test_blend_bm25_dense_alpha_one_is_pure_bm25_order() -> None:
    bm25 = {"a": 10.0, "b": 1.0}
    dense = {"a": 0.0, "b": 10.0}  # dense strongly prefers b
    ranked = blend_bm25_dense(bm25, dense, alpha=1.0)
    assert ranked[0] == "a"  # alpha=1.0 ignores dense entirely


def test_blend_bm25_dense_alpha_zero_is_pure_dense_order() -> None:
    bm25 = {"a": 10.0, "b": 1.0}
    dense = {"a": 0.0, "b": 10.0}
    ranked = blend_bm25_dense(bm25, dense, alpha=0.0)
    assert ranked[0] == "b"  # alpha=0.0 ignores bm25 entirely


def test_blend_bm25_dense_includes_a_chunk_present_in_only_one_channel() -> None:
    bm25 = {"a": 5.0}
    dense = {"b": 5.0}
    ranked = blend_bm25_dense(bm25, dense, alpha=0.5)
    assert set(ranked) == {"a", "b"}
