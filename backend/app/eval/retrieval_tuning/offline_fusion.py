"""Offline weighted BM25/vector fusion (Phase 6, PRD-109 / ARCH-040).

Experimental-only: queries Qdrant directly via two separate single-vector
requests (dense-only, sparse-only, `QdrantVectorStore.single_vector_search`)
and combines their scores client-side with a configurable BM25 weight. This
is entirely decoupled from `app.retrieval.hybrid.retrieve()`'s server-side
RRF fusion (ARCH-003) — that pipeline is never imported or modified here.
See PHASE6-PROPOSAL.md §2 and §7 for why: Qdrant's client API has no weight
knob for its own fusion, and wiring any result of this experiment into
production is a separate, later, conditional proposal (Phase 7), not this
one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.vectorstore import QdrantVectorStore


@dataclass(frozen=True)
class ScoredChunk:
    chunk_id: str
    bm25_score: float
    dense_score: float


def min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    """Raw BM25 (TF x IDF) is unbounded positive; dense score is a bounded
    cosine similarity — not comparable un-normalized. Normalized independently
    within each query's own candidate pool (not globally), since only the
    relative order within one query's retrieval matters here."""
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi == lo:
        # Every candidate scored identically (e.g. a single-candidate pool) —
        # no information to rank on; treat them as tied rather than /0.
        return dict.fromkeys(scores, 1.0)
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


# Promoted to public (PRD-112, DEVIATIONS.md #192): `app.eval.unified_ablation
# .blend` also needs this exact normalization for its own (Qdrant-ANN-free,
# brute-force) candidate scores. Re-exported under the old private name so
# this module's own existing call sites/tests are untouched.
_min_max_normalize = min_max_normalize


def fetch_candidate_scores(
    store: QdrantVectorStore,
    *,
    dense: list[float],
    sparse: dict,
    candidate_depth: int,
    flt: dict | None = None,
) -> list[ScoredChunk]:
    """Two single-vector Qdrant queries (dense-only, sparse-only), each to
    `candidate_depth` — independent of production's `settings.candidate_k`,
    since this experiment's candidate pool size is its own concern, not
    something that should silently track a production constant. A chunk
    present in only one list gets 0.0 for the missing side (never dropped),
    so a strong single-signal match can still win at a high enough weight."""
    dense_hits = store.single_vector_search(
        using="dense", query=dense, limit=candidate_depth, flt=flt
    )
    sparse_hits = store.single_vector_search(
        using="sparse", query=sparse, limit=candidate_depth, flt=flt
    )

    dense_norm = _min_max_normalize({h["chunk_id"]: h["score"] for h in dense_hits})
    sparse_norm = _min_max_normalize({h["chunk_id"]: h["score"] for h in sparse_hits})

    chunk_ids = set(dense_norm) | set(sparse_norm)
    return [
        ScoredChunk(
            chunk_id=cid,
            bm25_score=sparse_norm.get(cid, 0.0),
            dense_score=dense_norm.get(cid, 0.0),
        )
        for cid in chunk_ids
    ]


def weighted_rank(candidates: list[ScoredChunk], *, alpha: float) -> list[str]:
    """`alpha` is the BM25 weight; `1 - alpha` the vector weight. Returns
    chunk_ids ranked by `alpha*bm25_norm + (1-alpha)*dense_norm`, descending.
    Ties broken by `chunk_id` for a deterministic order (never left to
    incidental set/dict iteration order)."""
    ranked = sorted(
        candidates,
        key=lambda c: (-(alpha * c.bm25_score + (1 - alpha) * c.dense_score), c.chunk_id),
    )
    return [c.chunk_id for c in ranked]
