"""Embedding backend selection (ARCH-004; PRD-103).

`EMBEDDING_BACKEND` = local | gateway | stub. Dense embeddings for chunks and
queries; L2-normalized, cosine. Query/doc instruction prefixes applied if the
configured model needs them. Dense dimension is read from the model at startup
and asserted against the Qdrant collection.

Sparse (BM25) vectors are built in app.retrieval.hybrid, not here.
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.stub import stub_embed


def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    backend = get_settings().embedding_backend
    if backend == "stub":
        return stub_embed(texts)
    # Phase 2 "gateway" implementer: settings.embedding_gateway_url +
    # settings.embedding_gateway_api_key (Bearer auth) are already scaffolded
    # (DEVIATIONS.md #42) — embedding_model_id is the gateway's own model tag
    # in this mode, not the local-backend HuggingFace id.
    raise NotImplementedError(f"Phase 2: EMBEDDING_BACKEND={backend!r} (ARCH-004)")
