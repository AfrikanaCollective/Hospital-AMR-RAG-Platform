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
    # Phase 2 "local" implementer: sentence-transformers.CrossEncoder(
    # settings.reranker_model_id, max_length=settings.reranker_max_length,
    # device=<resolved from settings.reranker_device>) loaded once behind an
    # lru_cache singleton (mirrors get_settings()); score via
    # await asyncio.to_thread(model.predict, pairs, batch_size=
    # settings.reranker_batch_size) — .predict() blocks, never call it
    # directly from an async handler. Warm-load the singleton at app startup
    # (app/main.py lifespan) rather than on first request, per the ~15s
    # rerank-latency soft target in ARCHITECTURE.md §19 self-critique.
    # "gateway" implementer: same settings.embedding_gateway_* pattern as
    # ARCH-004 applies here if/when the gateway exposes a rerank endpoint —
    # see DEVIATIONS.md #43 for why that isn't assumed.
    raise NotImplementedError(f"Phase 2: RERANKER_BACKEND={backend!r} (ARCH-012)")
