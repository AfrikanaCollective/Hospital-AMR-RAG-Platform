"""Embedding backend selection (ARCH-004; PRD-103).

`EMBEDDING_BACKEND` = local | gateway | stub. Dense embeddings for chunks and
queries; L2-normalized, cosine. Query/doc instruction prefixes applied if the
configured model needs them. Dense dimension is read from the model at startup
and asserted against the Qdrant collection (`app.retrieval.vectorstore`).

Sparse (BM25) vectors are built in app.retrieval.sparse, not here.

**Not verified against real model weights in this session** (DEVIATIONS.md
#51): no network-downloaded model was run end to end here — `_load_local_model`
is a thin, standard `sentence-transformers` call, unit-tested via dependency
injection (`_LOCAL_MODEL_LOADER` is monkeypatchable) rather than against
`BAAI/bge-large-en-v1.5` itself. Confirm with a real load before relying on
this backend for a demo.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.llm.stub import stub_embed


class _EncodesTexts(Protocol):
    def encode(
        self, texts: list[str], *, normalize_embeddings: bool, **kw: object
    ) -> Iterable[Iterable[float]]: ...


def _load_local_model(model_id: str) -> _EncodesTexts:
    # noqa justification: sentence-transformers/torch are a multi-GB optional
    # extra (local-models); importing lazily keeps EMBEDDING_BACKEND=stub
    # environments from needing them at all.
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    # SentenceTransformer.encode's real overloaded stub is far wider than the
    # one call shape _EncodesTexts declares; narrowing it structurally isn't
    # practical, so this one boundary is trusted rather than typed exactly.
    return SentenceTransformer(model_id)  # type: ignore[return-value]


# Indirection point for tests: replace with a fake encoder to avoid a real
# network download / model load.
_LOCAL_MODEL_LOADER = _load_local_model


@lru_cache
def _get_local_model(model_id: str) -> _EncodesTexts:
    return _LOCAL_MODEL_LOADER(model_id)


def embed_texts(texts: list[str], *, is_query: bool = False) -> list[list[float]]:
    settings = get_settings()
    backend = settings.embedding_backend
    if backend == "stub":
        return stub_embed(texts)
    if backend == "local":
        prefix = settings.embedding_query_prefix if is_query else settings.embedding_doc_prefix
        prepared = [f"{prefix}{t}" for t in texts] if prefix else list(texts)
        model = _get_local_model(settings.embedding_model_id)
        vectors = model.encode(prepared, normalize_embeddings=True)
        return [list(v) for v in vectors]
    # "gateway" implementer: settings.embedding_gateway_url +
    # settings.embedding_gateway_api_key (Bearer auth) are already scaffolded
    # (DEVIATIONS.md #42) — embedding_model_id is the gateway's own model tag
    # in this mode, not the local-backend HuggingFace id.
    raise NotImplementedError(f"Phase 2: EMBEDDING_BACKEND={backend!r} (ARCH-004)")
