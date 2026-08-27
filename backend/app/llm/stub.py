"""Deterministic offline fake of the LLM gateway (PRD-106, PRD-G7).

Used when EMBEDDING_BACKEND / RERANKER_BACKEND == "stub" or the dev
`llm-gateway` compose service runs `app.llm.stub_server`. Canned, deterministic
outputs so unit tests and `docker compose up` need no network and no real model.

The stub NEVER fabricates guideline content: `chat()` returns a fixed
"no grounded answer available in stub mode" style payload. Real synthesis is
Phase 3 with a real gateway.
"""

from __future__ import annotations

import hashlib

from app.llm.gateway import ChatResult

_STUB_MODEL_ID = "stub-echo"


def stub_chat(*, system: str, messages: list[dict], **_params: object) -> ChatResult:  # noqa: ARG001
    return ChatResult(
        text="[stub] No grounded answer is produced in stub mode.",
        model_id=_STUB_MODEL_ID,
        usage={"stub": True},
    )


def stub_embed(texts: list[str], *, dim: int = 384, **_kw: object) -> list[list[float]]:
    """Deterministic pseudo-embedding from a hash — stable, not meaningful."""
    out: list[list[float]] = []
    for t in texts:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        vec = [((h[i % len(h)] / 255.0) * 2.0 - 1.0) for i in range(dim)]
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        out.append([x / norm for x in vec])
    return out


def stub_rerank(query: str, passages: list[str], **_kw: object) -> list[float]:
    """Cheap lexical overlap score in [0, 1] — deterministic, order-preserving-ish."""
    q = set(query.lower().split())
    scores = []
    for p in passages:
        toks = set(p.lower().split())
        scores.append(len(q & toks) / (len(q | toks) or 1))
    return scores
