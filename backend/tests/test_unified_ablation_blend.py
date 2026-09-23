"""Brute-force score blending for Level 3's BM25/SapBERT weighted-rank
fusion sweep (PRD-112). Restructured 2026-09-23 (DEVIATIONS.md #201):
MedCPT/RRF support (`combine_dense_scores`/`rrf_combine_scores`) removed."""

from __future__ import annotations

import numpy as np
import pytest

from app.config import get_settings
from app.eval.unified_ablation.blend import blend_bm25_dense, bm25_raw_scores, cosine_raw_scores
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


def test_blend_bm25_dense_weight_one_is_pure_bm25_order() -> None:
    bm25 = {"a": 10.0, "b": 1.0}
    dense = {"a": 0.0, "b": 10.0}  # dense strongly prefers b
    ranked = blend_bm25_dense(bm25, dense, bm25_weight=1.0)
    assert ranked[0] == "a"  # bm25_weight=1.0 ignores dense entirely


def test_blend_bm25_dense_weight_zero_is_pure_dense_order() -> None:
    bm25 = {"a": 10.0, "b": 1.0}
    dense = {"a": 0.0, "b": 10.0}
    ranked = blend_bm25_dense(bm25, dense, bm25_weight=0.0)
    assert ranked[0] == "b"  # bm25_weight=0.0 ignores bm25 entirely


def test_blend_bm25_dense_includes_a_chunk_present_in_only_one_channel() -> None:
    bm25 = {"a": 5.0}
    dense = {"b": 5.0}
    ranked = blend_bm25_dense(bm25, dense, bm25_weight=0.5)
    assert set(ranked) == {"a", "b"}
