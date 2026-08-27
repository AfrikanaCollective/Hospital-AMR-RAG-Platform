"""VectorStore adapter (ARCH-002). Qdrant implementation.

Guideline chunks: named vectors `dense` + `sparse`, server-side RRF fusion,
payload filtering for access scoping (status, topic_tags, allowed_doc_ids).
If PATIENT_RECORD_VECTORS_ENABLED is ever set, record vectors go in a SEPARATE
collection with mandatory patient_id payload filtering (ARCH-023).

The adapter interface keeps a swap path open (DEVIATIONS.md #1).
"""

from __future__ import annotations

from typing import Protocol


class VectorStore(Protocol):
    def upsert_chunks(self, points: list[dict]) -> None: ...
    def hybrid_search(
        self, *, dense: list[float], sparse: dict, limit: int, flt: dict | None
    ) -> list[dict]: ...
    def get_by_ids(self, ids: list[str]) -> list[dict]: ...


class QdrantVectorStore:
    def __init__(self, url: str, api_key: str, collection: str) -> None:
        self.url = url
        self.api_key = api_key
        self.collection = collection

    def upsert_chunks(self, points: list[dict]) -> None:
        raise NotImplementedError("Phase 2 (ARCH-002)")

    def hybrid_search(self, *, dense, sparse, limit, flt=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Phase 2 (ARCH §7.2-7.3)")

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        raise NotImplementedError("Phase 2")
