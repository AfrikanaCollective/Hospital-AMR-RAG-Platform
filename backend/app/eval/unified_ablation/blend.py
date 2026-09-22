"""Brute-force score blending for Level 3's dense-bearing arms
(UNIFIED-ABLATION-PROPOSAL.md §3.3, §4 points 1/6; PRD-112).

Reuses `retrieval_tuning.offline_fusion.weighted_rank`/`ScoredChunk`/
`min_max_normalize` **unchanged** — those are already pure,
Qdrant-independent functions once a candidate's `bm25_score`/`dense_score`
are in hand. `offline_fusion.fetch_candidate_scores` (the *other* half of
that module) is Qdrant-ANN-specific — two server-side searches against the
one production embedding — and can't be reused for SapBERT/MedCPT, which
`model_ablation.ablation` deliberately never writes to Qdrant (it ranks
brute-force over the whole in-memory corpus instead, `_bm25_rank`/
`_cosine_rank`). This module supplies that brute-force-corpus equivalent:
raw BM25 scores via the same Qdrant sparse-vector call `_bm25_rank` already
makes (just returning scores instead of only a sorted ranking), and raw
cosine scores mirroring `_cosine_rank`'s own query-vector normalization
exactly (same reason — that function only returns the sorted ranking, and
a weighted blend needs the underlying scores).
"""

from __future__ import annotations

import numpy as np

from app.eval.retrieval_tuning.offline_fusion import ScoredChunk, min_max_normalize, weighted_rank
from app.retrieval.sparse import query_sparse_vector
from app.retrieval.vectorstore import QdrantVectorStore


def bm25_raw_scores(
    store: QdrantVectorStore, question_text: str, chunk_ids: list[str]
) -> dict[str, float]:
    """Raw (un-normalized) BM25 score per chunk that scored at all, full
    corpus depth. A chunk sharing no term with the query is simply absent
    from the result — `min_max_normalize`/`ScoredChunk` construction fills
    the gap with 0.0 the same way `fetch_candidate_scores` already does for
    its own two channels, not something this function needs to do itself."""
    sparse = query_sparse_vector(question_text)
    hits = store.single_vector_search(using="sparse", query=sparse, limit=len(chunk_ids))
    return {h["chunk_id"]: h["score"] for h in hits}


def cosine_raw_scores(
    query_vec: list[float], chunk_matrix: np.ndarray, chunk_ids: list[str]
) -> dict[str, float]:
    """Raw cosine similarity per chunk — mirrors
    `model_ablation.ablation._cosine_rank`'s own query-vector normalization
    exactly, but returns the full `{chunk_id: score}` dict instead of only
    the sorted ranking."""
    q = np.asarray(query_vec, dtype=np.float64)
    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm
    sims = chunk_matrix @ q
    return dict(zip(chunk_ids, sims.tolist(), strict=True))


def combine_dense_scores(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    """Mean of two ALREADY min-max-normalized dense-channel scores
    (UNIFIED-ABLATION-PROPOSAL.md §3.3/§4 point 6 — the SapBERT+MedCPT
    combined arm) — a flagged judgment call, not a second RRF layer inside
    the alpha blend, which would mix a rank-based and a score-based
    combination mechanism within one arm. `a`/`b` are normalized here
    (idempotent if already normalized), not assumed pre-normalized by the
    caller."""
    a_norm = min_max_normalize(a)
    b_norm = min_max_normalize(b)
    chunk_ids = set(a_norm) | set(b_norm)
    return {cid: (a_norm.get(cid, 0.0) + b_norm.get(cid, 0.0)) / 2 for cid in chunk_ids}


def blend_bm25_dense(
    bm25_scores: dict[str, float],
    dense_scores: dict[str, float],
    *,
    alpha: float,
) -> list[str]:
    """One (raw or already-combined) dense channel, alpha-blended against
    BM25 — both independently min-max-normalized first (matching
    `fetch_candidate_scores`'s own convention exactly), then handed to
    `weighted_rank`, reused unchanged. `alpha` is the BM25 weight, `1-alpha`
    the dense weight (`weighted_rank`'s own existing convention)."""
    bm25_norm = min_max_normalize(bm25_scores)
    dense_norm = min_max_normalize(dense_scores)
    chunk_ids = set(bm25_norm) | set(dense_norm)
    candidates = [
        ScoredChunk(
            chunk_id=cid,
            bm25_score=bm25_norm.get(cid, 0.0),
            dense_score=dense_norm.get(cid, 0.0),
        )
        for cid in chunk_ids
    ]
    return weighted_rank(candidates, alpha=alpha)
