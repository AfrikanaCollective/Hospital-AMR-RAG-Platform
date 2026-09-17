"""Brute-force in-memory embedding ablation: SapBERT+BM25, MedCPT+BM25,
SapBERT+MedCPT+BM25 (PRD-110 / ARCH-041,
PHASE2-EMBEDDING-ABLATION-PROPOSAL.md).

Reuses `app.eval.retrieval_tuning.sweep.fetch_calibration_questions` and
`app.eval.metrics.precision_recall_at_k`/`mrr` unchanged — this module only
supplies alternative *rankings* to score against the eval-question set's
known gold chunks.

**Fully offline, no persistence** (proposal §2): the live guideline
collection has 314 points (confirmed 2026-09-17) — small enough to rank
*exactly* by brute-force cosine similarity over the whole corpus, so no
ANN/candidate-depth truncation is needed and no SapBERT/MedCPT vector is
ever written to Qdrant; they exist only for the duration of one script run.

**RRF combine is reimplemented client-side** (proposal §5): SapBERT/MedCPT
aren't in Qdrant, so there's no collection to run Qdrant's own RRF against.
Uses the standard Cormack et al. (2009) formula with `settings.rrf_k`
(default 60 — the same constant `vectorstore.py`'s docstring documents as
"matching Qdrant's own internal constant", DEVIATIONS.md #49) — this is not
expected to reproduce Qdrant's fused scores number-for-number, only to be a
reasonable, consistently-applied combine across the three ablation arms.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.eval.metrics import mrr, precision_recall_at_k
from app.eval.model_ablation.encoders import Encoder, get_medcpt_encoders, get_sapbert_encoder
from app.eval.retrieval_tuning.sweep import (
    SweepQuestion,
    fetch_calibration_questions,
)
from app.ingestion.embed import embed_texts
from app.retrieval.hybrid import _expand_abbreviations
from app.retrieval.sparse import query_sparse_vector
from app.retrieval.vectorstore import QdrantVectorStore

K_VALUES: tuple[int, ...] = tuple(range(2, 61, 2))  # matches retrieval_tuning.sweep.K_VALUES
MRR_K = 24  # matches retrieval_tuning.sweep.MRR_K, for direct comparability

ARMS: tuple[str, ...] = ("sapbert_bm25", "medcpt_bm25", "sapbert_medcpt_bm25")
REFERENCE_ARM = "rrf_production"
ALL_ARMS: tuple[str, ...] = (*ARMS, REFERENCE_ARM)


@dataclass(frozen=True)
class Corpus:
    chunk_ids: list[str]
    texts: list[str]


def fetch_corpus(store: QdrantVectorStore) -> Corpus:
    """Every guideline chunk, once per run — see module docstring for why
    this is feasible without an ANN index (314 points, 2026-09-17)."""
    points = store.scroll_all()
    return Corpus(
        chunk_ids=[p["chunk_id"] for p in points],
        texts=[p.get("text", "") for p in points],
    )


def _l2_normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _cosine_rank(
    query_vec: list[float], chunk_matrix: np.ndarray, chunk_ids: list[str]
) -> list[str]:
    q = np.asarray(query_vec, dtype=np.float64)
    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm
    sims = chunk_matrix @ q
    order = np.argsort(-sims, kind="stable")
    return [chunk_ids[i] for i in order]


def _bm25_rank(store: QdrantVectorStore, question_text: str, chunk_ids: list[str]) -> list[str]:
    """Existing `sparse` named vector already in Qdrant (unchanged from
    Phase 6) — no new BM25 computation. A chunk sharing no term with the
    query gets no score from Qdrant's sparse query at all; such chunks are
    appended, in a deterministic (sorted) order, after every chunk that did
    score — they have zero lexical signal, so last is the correct rank, but
    the tie order among them must not depend on incidental iteration order."""
    sparse = query_sparse_vector(question_text)
    hits = store.single_vector_search(using="sparse", query=sparse, limit=len(chunk_ids))
    ranked = [h["chunk_id"] for h in hits]
    missing = sorted(set(chunk_ids) - set(ranked))
    return ranked + missing


def _rrf_combine(rankings: list[list[str]], *, rrf_k: int) -> list[str]:
    """Cormack et al. (2009): score(d) = sum_r 1 / (rrf_k + rank_r(d) + 1),
    1-indexed rank. Every ranking here is already complete over the whole
    corpus (no missing chunks), so no separate "unranked" handling is
    needed, unlike a real ANN-truncated candidate list."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank + 1)
    return sorted(scores, key=lambda cid: (-scores[cid], cid))


@dataclass(frozen=True)
class QuestionArmRankings:
    question_id: str
    gold_chunk_ids: frozenset[str]
    rankings: dict[str, list[str]]  # arm name -> full ranked chunk_ids


def rank_question(
    store: QdrantVectorStore,
    question: SweepQuestion,
    corpus: Corpus,
    *,
    sapbert_encoder: Encoder,
    sapbert_chunk_matrix: np.ndarray,
    medcpt_query_encoder: Encoder,
    medcpt_chunk_matrix: np.ndarray,
    rrf_k: int,
) -> QuestionArmRankings:
    """Embeds/queries this question once per channel and produces every
    ablation arm's combined ranking plus the fresh production RRF reference
    (recomputed live, not a hardcoded historical number — see
    PHASE2-EMBEDDING-ABLATION-PROPOSAL.md §5's "reference points" note)."""
    expanded = _expand_abbreviations(question.text)

    bm25_rank = _bm25_rank(store, expanded, corpus.chunk_ids)

    sapbert_qvec = sapbert_encoder.encode([expanded])[0]
    sapbert_rank = _cosine_rank(sapbert_qvec, sapbert_chunk_matrix, corpus.chunk_ids)

    medcpt_qvec = medcpt_query_encoder.encode([expanded])[0]
    medcpt_rank = _cosine_rank(medcpt_qvec, medcpt_chunk_matrix, corpus.chunk_ids)

    dense = embed_texts([expanded], is_query=True)[0]
    sparse = query_sparse_vector(expanded)
    n = len(corpus.chunk_ids)
    prod_hits = store.hybrid_search(dense=dense, sparse=sparse, prefetch_limit=n, limit=n)
    rrf_production = [h["chunk_id"] for h in prod_hits]

    rankings = {
        "sapbert_bm25": _rrf_combine([sapbert_rank, bm25_rank], rrf_k=rrf_k),
        "medcpt_bm25": _rrf_combine([medcpt_rank, bm25_rank], rrf_k=rrf_k),
        "sapbert_medcpt_bm25": _rrf_combine([sapbert_rank, medcpt_rank, bm25_rank], rrf_k=rrf_k),
        REFERENCE_ARM: rrf_production,
    }
    return QuestionArmRankings(
        question_id=question.question_id,
        gold_chunk_ids=question.gold_chunk_ids,
        rankings=rankings,
    )


@dataclass(frozen=True)
class AblationResult:
    # each row: {"k": int, "arm": str, "recall": float}
    recall_rows: list[dict]
    # each row: {"arm": str, "mrr": float}
    mrr_rows: list[dict]
    n_questions: int


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# Bootstrap CI for panel B (DEVIATIONS.md #132, follow-up request). Percentile
# method: resample the per-question MRR scores with replacement _BOOTSTRAP_N
# times, take each resample's mean, then the [2.5, 97.5] percentiles of that
# distribution as the 95% interval. A fixed seed makes repeated report runs
# reproducible rather than jittering the CI on every regenerate — both
# constants are judgment calls (a round resample count and an arbitrary but
# fixed seed), not derived from anything.
_BOOTSTRAP_N = 10_000
_BOOTSTRAP_SEED = 1234
_BOOTSTRAP_CI = 0.95


def _bootstrap_ci(scores: list[float], *, rng: np.random.Generator) -> tuple[float, float]:
    """95% percentile-bootstrap CI on the mean of `scores`. With very few
    scores (e.g. a 2-question unit-test fixture) this is a wide, not
    statistically meaningful interval — expected, not a bug; the real report
    runs it over 67 real questions."""
    if not scores:
        return 0.0, 0.0
    arr = np.asarray(scores, dtype=np.float64)
    resampled = rng.choice(arr, size=(_BOOTSTRAP_N, len(arr)), replace=True)
    means = resampled.mean(axis=1)
    lo_pct = (1 - _BOOTSTRAP_CI) / 2 * 100
    hi_pct = 100 - lo_pct
    return float(np.percentile(means, lo_pct)), float(np.percentile(means, hi_pct))


def run_ablation(rankings: list[QuestionArmRankings]) -> AblationResult:
    """Pure aggregation over already-computed rankings — no I/O, mirroring
    `retrieval_tuning.sweep.run_sweep`'s split (fast, offline-testable)."""
    recall_rows: list[dict] = []
    for k in K_VALUES:
        for arm in ALL_ARMS:
            recalls = [
                precision_recall_at_k(r.rankings[arm], set(r.gold_chunk_ids), k)[1]
                for r in rankings
            ]
            recall_rows.append({"k": k, "arm": arm, "recall": _mean(recalls)})

    mrr_rows: list[dict] = []
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    for arm in ALL_ARMS:
        scores = [mrr(r.rankings[arm][:MRR_K], set(r.gold_chunk_ids)) for r in rankings]
        ci_low, ci_high = _bootstrap_ci(scores, rng=rng)
        mrr_rows.append({"arm": arm, "mrr": _mean(scores), "ci_low": ci_low, "ci_high": ci_high})

    return AblationResult(recall_rows=recall_rows, mrr_rows=mrr_rows, n_questions=len(rankings))


def run_full_ablation(session: Session, store: QdrantVectorStore) -> AblationResult:
    """Wires fetch -> embed -> rank -> aggregate for a real (or stub) run.
    Kept separate from `run_ablation` so the aggregation math stays testable
    without a Qdrant/model dependency (CLAUDE.md §5)."""
    settings = get_settings()
    questions = fetch_calibration_questions(session)
    if not questions:
        return AblationResult(recall_rows=[], mrr_rows=[], n_questions=0)
    corpus = fetch_corpus(store)

    sapbert_encoder = get_sapbert_encoder()
    medcpt_query_encoder, medcpt_article_encoder = get_medcpt_encoders()

    sapbert_chunk_matrix = _l2_normalize_rows(
        np.asarray(sapbert_encoder.encode(corpus.texts), dtype=np.float64)
    )
    medcpt_chunk_matrix = _l2_normalize_rows(
        np.asarray(medcpt_article_encoder.encode(corpus.texts), dtype=np.float64)
    )

    rankings = [
        rank_question(
            store,
            q,
            corpus,
            sapbert_encoder=sapbert_encoder,
            sapbert_chunk_matrix=sapbert_chunk_matrix,
            medcpt_query_encoder=medcpt_query_encoder,
            medcpt_chunk_matrix=medcpt_chunk_matrix,
            rrf_k=settings.rrf_k,
        )
        for q in questions
    ]
    return run_ablation(rankings)
