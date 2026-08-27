"""Cross-encoder reranking (ARCH-012; PRD-103).

`RERANKER_BACKEND` = local | gateway | stub. Scores (query, chunk.text) pairs
for the fused candidate set -> TOP_K. Model id from config; none hardcoded.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.stub import stub_rerank


def rerank(query: str, passages: list[str]) -> list[float]:
    backend = get_settings().reranker_backend
    if backend == "stub":
        return stub_rerank(query, passages)
    raise NotImplementedError(f"Phase 2: RERANKER_BACKEND={backend!r} (ARCH-012)")
