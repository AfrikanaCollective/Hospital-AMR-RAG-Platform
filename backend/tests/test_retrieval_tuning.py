"""Phase 6 offline weight-sweep tooling (PRD-109 / ARCH-040), run against
qdrant-client's embedded in-memory mode with the offline stub embedding
backend — no network, no real models, no real Postgres (CLAUDE.md §5). Mirrors
tests/test_hybrid_retrieve.py's fixture pattern.

`fetch_calibration_questions` (a plain SQLAlchemy `select` against
`eval.eval_question`) is not covered here — it needs a real Postgres for a
meaningful test, same as other DB-query functions in this codebase; verify it
against a real ephemeral Postgres before relying on it (see
PHASE6-PROPOSAL.md §8)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.eval.metrics import mrr, precision_recall_at_k
from app.eval.retrieval_tuning.offline_fusion import (
    ScoredChunk,
    _min_max_normalize,
    fetch_candidate_scores,
    weighted_rank,
)
from app.eval.retrieval_tuning.sweep import (
    ALPHA_VALUES,
    MRR_K,
    QuestionRankings,
    rank_question,
    run_sweep,
)
from app.ingestion.embed import embed_texts
from app.retrieval.sparse import doc_sparse_vector
from app.retrieval.vectorstore import QdrantVectorStore
from app.schemas.enums import ExpectedOutcome, Provenance
from tests.test_hybrid_retrieve import _seed_chunk

_DENSE_DIM = 384


@pytest.fixture(autouse=True)
def _stub_backends(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("RERANKER_BACKEND", "stub")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="retrieval_tuning_test")
    s.ensure_collection(dense_dim=_DENSE_DIM)
    return s


def test_min_max_normalize_maps_range_to_zero_one() -> None:
    out = _min_max_normalize({"a": 1.0, "b": 3.0, "c": 5.0})
    assert out == {"a": 0.0, "b": 0.5, "c": 1.0}


def test_min_max_normalize_ties_when_all_scores_equal() -> None:
    out = _min_max_normalize({"a": 2.0, "b": 2.0})
    assert out == {"a": 1.0, "b": 1.0}


def test_min_max_normalize_empty_is_empty() -> None:
    assert _min_max_normalize({}) == {}


def test_weighted_rank_alpha_one_is_bm25_only_order() -> None:
    candidates = [
        ScoredChunk(chunk_id="lex_wins", bm25_score=1.0, dense_score=0.0),
        ScoredChunk(chunk_id="sem_wins", bm25_score=0.0, dense_score=1.0),
    ]
    assert weighted_rank(candidates, alpha=1.0) == ["lex_wins", "sem_wins"]


def test_weighted_rank_alpha_zero_is_dense_only_order() -> None:
    candidates = [
        ScoredChunk(chunk_id="lex_wins", bm25_score=1.0, dense_score=0.0),
        ScoredChunk(chunk_id="sem_wins", bm25_score=0.0, dense_score=1.0),
    ]
    assert weighted_rank(candidates, alpha=0.0) == ["sem_wins", "lex_wins"]


def test_weighted_rank_breaks_ties_by_chunk_id() -> None:
    candidates = [
        ScoredChunk(chunk_id="b", bm25_score=0.5, dense_score=0.5),
        ScoredChunk(chunk_id="a", bm25_score=0.5, dense_score=0.5),
    ]
    assert weighted_rank(candidates, alpha=0.5) == ["a", "b"]


def test_fetch_candidate_scores_pairs_dense_and_sparse_hits(store: QdrantVectorStore) -> None:
    target_text = "Blood cultures are recommended before starting antimicrobials."
    _seed_chunk(store, 1, chunk_id="c1", text=target_text)
    _seed_chunk(store, 2, chunk_id="c2", text="Vitamin K is given to newborns shortly after birth.")

    dense = embed_texts([target_text], is_query=True)[0]
    sparse = doc_sparse_vector(target_text)
    candidates = fetch_candidate_scores(store, dense=dense, sparse=sparse, candidate_depth=10)

    by_id = {c.chunk_id: c for c in candidates}
    assert by_id["c1"].bm25_score == pytest.approx(1.0)
    assert by_id["c1"].dense_score == pytest.approx(1.0)


def test_rank_question_returns_every_alpha_and_rrf_baseline(store: QdrantVectorStore) -> None:
    from app.eval.retrieval_tuning.sweep import SweepQuestion

    target_text = "Blood cultures are recommended before starting antimicrobials."
    _seed_chunk(store, 1, chunk_id="c1", text=target_text)
    _seed_chunk(store, 2, chunk_id="c2", text="Vitamin K is given to newborns shortly after birth.")

    question = SweepQuestion(question_id="q1", text=target_text, gold_chunk_ids=frozenset({"c1"}))
    result = rank_question(store, question)

    assert set(result.weighted_by_alpha) == set(ALPHA_VALUES)
    assert result.weighted_by_alpha[1.0][0] == "c1"  # exact lexical match wins at alpha=1
    assert result.rrf_baseline[0] == "c1"


def test_run_sweep_recall_and_mrr_on_a_small_known_grid() -> None:
    # Two questions: one where alpha=1 (BM25) ranks the gold chunk first and
    # alpha=0 (dense) buries it; one the other way round. A mid-alpha sweep
    # should land strictly between the two single-signal extremes.
    rankings = [
        QuestionRankings(
            question_id="q1",
            gold_chunk_ids=frozenset({"gold1"}),
            weighted_by_alpha={
                0.0: ["distractor", "gold1"],
                1.0: ["gold1", "distractor"],
            },
            rrf_baseline=["gold1", "distractor"],
        ),
        QuestionRankings(
            question_id="q2",
            gold_chunk_ids=frozenset({"gold2"}),
            weighted_by_alpha={
                0.0: ["gold2", "distractor"],
                1.0: ["distractor", "gold2"],
            },
            rrf_baseline=["distractor", "gold2"],
        ),
    ]

    result = run_sweep(
        [
            QuestionRankings(
                question_id=r.question_id,
                gold_chunk_ids=r.gold_chunk_ids,
                weighted_by_alpha={
                    a: (r.weighted_by_alpha[0.0] if a < 0.5 else r.weighted_by_alpha[1.0])
                    for a in ALPHA_VALUES
                },
                rrf_baseline=r.rrf_baseline,
            )
            for r in rankings
        ]
    )

    recall_at_1_alpha_0 = next(
        row["recall"] for row in result.recall_rows if row["k"] == 2 and row["alpha"] == 0.0
    )
    recall_at_1_alpha_1 = next(
        row["recall"] for row in result.recall_rows if row["k"] == 2 and row["alpha"] == 1.0
    )
    # Sanity check the aggregation against the metrics module directly rather
    # than a hand-computed constant, so this test breaks if run_sweep ever
    # stops delegating to app.eval.metrics.
    expected = sum(
        precision_recall_at_k(r.weighted_by_alpha[0.0], set(r.gold_chunk_ids), 2)[1]
        for r in rankings
    ) / len(rankings)
    assert recall_at_1_alpha_0 == pytest.approx(expected)
    assert recall_at_1_alpha_1 == pytest.approx(expected)  # symmetric by construction

    rrf_recall = next(
        row["recall"] for row in result.recall_rows if row["k"] == 2 and row["alpha"] == "rrf"
    )
    assert rrf_recall == pytest.approx(1.0)  # gold chunk is top-2 in both questions' rrf_baseline

    mrr_alpha_1 = next(row["mrr"] for row in result.mrr_rows if row["alpha"] == 1.0)
    expected_mrr = sum(
        mrr(r.weighted_by_alpha[1.0][:MRR_K], set(r.gold_chunk_ids)) for r in rankings
    ) / len(rankings)
    assert mrr_alpha_1 == pytest.approx(expected_mrr)

    assert result.n_questions == 2


def test_expected_outcome_and_provenance_enums_used_by_the_eval_query_filter() -> None:
    # Guards the literal values fetch_calibration_questions filters on in its
    # SQLAlchemy `select` (not itself exercised here — see module docstring).
    assert ExpectedOutcome.WELL_SUPPORTED == "well_supported"
    assert Provenance.AUTO_GENERATED == "auto_generated"
