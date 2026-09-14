"""QdrantVectorStore, run against qdrant-client's embedded in-memory mode
(no server, no network — ARCH-002)."""

from __future__ import annotations

import pytest

from app.retrieval.vectorstore import QdrantVectorStore


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="guideline_chunks_test")
    s.ensure_collection(dense_dim=4)
    return s


def _point(
    id_: int,
    dense: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    **payload: object,
) -> dict:
    return {
        "id": id_,
        "dense": dense,
        "sparse": {"indices": sparse_indices, "values": sparse_values},
        "payload": {"status": "active", **payload},
    }


def test_ensure_collection_is_idempotent(store: QdrantVectorStore) -> None:
    store.ensure_collection(dense_dim=4)  # second call: asserts, doesn't recreate


def test_ensure_collection_rejects_dimension_mismatch(store: QdrantVectorStore) -> None:
    with pytest.raises(RuntimeError, match="dense dim"):
        store.ensure_collection(dense_dim=8)


def test_upsert_and_hybrid_search_returns_scored_points(store: QdrantVectorStore) -> None:
    store.upsert_chunks(
        [
            _point(1, [1.0, 0.0, 0.0, 0.0], [0, 1], [1.0, 0.5], chunk_id="c1"),
            _point(2, [0.0, 1.0, 0.0, 0.0], [1, 2], [0.3, 0.9], chunk_id="c2"),
        ]
    )
    results = store.hybrid_search(
        dense=[1.0, 0.0, 0.0, 0.0],
        sparse={"indices": [1], "values": [1.0]},
        prefetch_limit=5,
        limit=5,
    )
    assert {r["chunk_id"] for r in results} == {"c1", "c2"}
    assert results[0]["chunk_id"] == "c1"  # closer on both dense and sparse


def test_hybrid_search_respects_status_filter(store: QdrantVectorStore) -> None:
    store.upsert_chunks(
        [
            _point(1, [1.0, 0.0, 0.0, 0.0], [0], [1.0], chunk_id="c1", status="active"),
            _point(2, [1.0, 0.0, 0.0, 0.0], [0], [1.0], chunk_id="c2", status="withdrawn"),
        ]
    )
    results = store.hybrid_search(
        dense=[1.0, 0.0, 0.0, 0.0],
        sparse={"indices": [0], "values": [1.0]},
        prefetch_limit=5,
        limit=5,
        flt={"status": "active"},
    )
    assert [r["chunk_id"] for r in results] == ["c1"]


def test_hybrid_search_respects_allowed_doc_ids_filter(store: QdrantVectorStore) -> None:
    store.upsert_chunks(
        [
            _point(1, [1.0, 0.0, 0.0, 0.0], [0], [1.0], chunk_id="c1", document_id="doc-a"),
            _point(2, [1.0, 0.0, 0.0, 0.0], [0], [1.0], chunk_id="c2", document_id="doc-b"),
        ]
    )
    results = store.hybrid_search(
        dense=[1.0, 0.0, 0.0, 0.0],
        sparse={"indices": [0], "values": [1.0]},
        prefetch_limit=5,
        limit=5,
        flt={"allowed_doc_ids": ["doc-a"]},
    )
    assert [r["chunk_id"] for r in results] == ["c1"]


def test_get_by_ids(store: QdrantVectorStore) -> None:
    store.upsert_chunks([_point(1, [1.0, 0.0, 0.0, 0.0], [0], [1.0], chunk_id="c1")])
    got = store.get_by_ids([1])
    assert len(got) == 1
    assert got[0]["chunk_id"] == "c1"
