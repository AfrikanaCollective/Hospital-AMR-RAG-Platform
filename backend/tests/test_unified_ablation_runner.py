"""The 16-arm x alpha x K sweep, offline (PRD-112 / ARCH-043) — exercises
`sweep_questions` (the testable core), not `run_unified_ablation` (its thin
Postgres-session-touching wrapper, same split precedent as
`app.eval.retrieval_tuning.sweep.run_sweep`/`run_full_ablation` and
`app.eval.model_ablation.ablation.run_ablation`/`run_full_ablation` — see
each module's own test file's docstring)."""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from app.config import get_settings
from app.eval.ablation_config import ALL_ARMS
from app.eval.model_ablation.ablation import _l2_normalize_rows, fetch_corpus
from app.eval.model_ablation.encoders import get_medcpt_encoders, get_sapbert_encoder
from app.eval.retrieval_tuning.sweep import SweepQuestion
from app.eval.unified_ablation.per_query import PerQueryResult
from app.eval.unified_ablation.runner import sweep_questions
from app.records.concepts import ConceptVocabulary
from app.retrieval.vectorstore import QdrantVectorStore
from tests.test_hybrid_retrieve import _seed_chunk

_DENSE_DIM = 384

RECORD_ID = uuid.uuid4()
RECORD = {
    "record_id": "SYNREC-TEST",
    "mrn": "SYN-TEST",
    "sex": "male",
    "encounter": {"gestational_age_weeks": 34.0, "day_of_life": 1, "care_setting": "NBU"},
    "examination_findings": [
        {"name": "grunting", "present": True},
        {"name": "convulsions", "present": False},
    ],
    "vitals": [{"resp_rate_bpm": 65.0}],
}


@pytest.fixture(autouse=True)
def _stub_backends(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("RERANKER_BACKEND", "stub")
    monkeypatch.setenv("MODEL_ABLATION_BACKEND", "stub")
    # Small grid: keeps the exact-row-count assertions below readable.
    # bm25 has no alpha dimension (1 fixed value); the 3 dense arms each get
    # both configured alphas -> 1 + 2 + 2 + 2 = 7 arm-alpha combos per
    # (level1, level2) pair, x 2 k-values x 4 (level1 x level2) pairs = 56
    # rows for one question.
    monkeypatch.setenv("ABLATION_K_VALUES", "2,4")
    monkeypatch.setenv("ABLATION_ALPHA_VALUES", "0.0,1.0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="unified_ablation_runner_test")
    s.ensure_collection(dense_dim=_DENSE_DIM)
    _seed_chunk(
        store=s,
        point_id=1,
        chunk_id="gold-chunk",
        text="Antibiotics are recommended for suspected neonatal sepsis with grunting.",
    )
    _seed_chunk(
        store=s,
        point_id=2,
        chunk_id="other-chunk",
        text="Routine newborn care does not require antibiotics.",
    )
    return s


def _sweep(
    store: QdrantVectorStore,
    *,
    questions: list[SweepQuestion],
    record_index: dict,
    vocabulary: ConceptVocabulary | None = None,
) -> list[PerQueryResult]:
    corpus = fetch_corpus(store)
    sapbert_encoder = get_sapbert_encoder()
    medcpt_query_encoder, medcpt_article_encoder = get_medcpt_encoders()
    sapbert_matrix = _l2_normalize_rows(np.asarray(sapbert_encoder.encode(corpus.texts)))
    medcpt_matrix = _l2_normalize_rows(np.asarray(medcpt_article_encoder.encode(corpus.texts)))
    return list(
        sweep_questions(
            questions,
            store,
            corpus,
            sapbert_encoder=sapbert_encoder,
            sapbert_chunk_matrix=sapbert_matrix,
            medcpt_query_encoder=medcpt_query_encoder,
            medcpt_chunk_matrix=medcpt_matrix,
            record_index=record_index,
            vocabulary=vocabulary,
            experiment_id="exp-1",
            k_grid=get_settings().ablation_k_values_tuple,
        )
    )


def test_sweep_produces_exactly_the_expected_row_count_for_one_question(
    store: QdrantVectorStore,
) -> None:
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=RECORD_ID,
    )
    rows = _sweep(store, questions=[question], record_index={RECORD_ID: RECORD})
    assert len(rows) == 56  # see the grid comment in _stub_backends above


def test_sweep_covers_all_16_arms_and_both_level1_level2_conditions(
    store: QdrantVectorStore,
) -> None:
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=RECORD_ID,
    )
    rows = _sweep(store, questions=[question], record_index={RECORD_ID: RECORD})
    seen_arms = {(r.level1_condition, r.level2_condition, r.level3_condition) for r in rows}
    expected_arms = {(a.level1, a.level2, a.level3) for a in ALL_ARMS}
    assert seen_arms == expected_arms


def test_question_with_no_resolvable_source_record_is_skipped(store: QdrantVectorStore) -> None:
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=uuid.uuid4(),  # not in record_index
    )
    rows = _sweep(store, questions=[question], record_index={})
    assert rows == []


def test_bm25_arm_rows_always_carry_the_fixed_pure_bm25_alpha(store: QdrantVectorStore) -> None:
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=RECORD_ID,
    )
    rows = _sweep(store, questions=[question], record_index={RECORD_ID: RECORD})
    bm25_rows = [r for r in rows if r.level3_condition == "bm25"]
    assert bm25_rows  # non-empty
    assert all(r.alpha == 1.0 for r in bm25_rows)


def test_present_only_and_all_assessed_produce_different_query_text(
    store: QdrantVectorStore,
) -> None:
    """The record has an assessed-absent finding (convulsions) -- Level 1
    must actually differ between the two conditions for this record,
    otherwise the whole comparison would be vacuous."""
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=RECORD_ID,
    )
    rows = _sweep(store, questions=[question], record_index={RECORD_ID: RECORD})
    present_only_texts = {r.query_text for r in rows if r.level1_condition == "present_only"}
    all_assessed_texts = {r.query_text for r in rows if r.level1_condition == "all_assessed"}
    assert present_only_texts != all_assessed_texts
    assert not any("did NOT have" in t for t in present_only_texts)
    assert any("did NOT have convulsions" in t for t in all_assessed_texts)


def test_reciprocal_rank_at_k_and_first_relevant_rank_are_consistent(
    store: QdrantVectorStore,
) -> None:
    question = SweepQuestion(
        question_id="q1",
        text="ignored",
        gold_chunk_ids=frozenset({"gold-chunk"}),
        source_record_id=RECORD_ID,
    )
    rows = _sweep(store, questions=[question], record_index={RECORD_ID: RECORD})
    for row in rows:
        if row.first_relevant_rank is not None and row.first_relevant_rank <= row.k:
            assert row.reciprocal_rank_at_k == pytest.approx(1.0 / row.first_relevant_rank)
        else:
            assert row.reciprocal_rank_at_k == 0.0
        assert row.relevant_ids == ["gold-chunk"]
        assert len(row.retrieved_ids) <= row.k


def test_multiple_questions_each_produce_their_own_full_row_set(store: QdrantVectorStore) -> None:
    record_id_2 = uuid.uuid4()
    record_2 = {**RECORD, "record_id": "SYNREC-TEST-2"}
    questions = [
        SweepQuestion(
            question_id="q1",
            text="ignored",
            gold_chunk_ids=frozenset({"gold-chunk"}),
            source_record_id=RECORD_ID,
        ),
        SweepQuestion(
            question_id="q2",
            text="ignored",
            gold_chunk_ids=frozenset({"other-chunk"}),
            source_record_id=record_id_2,
        ),
    ]
    rows = _sweep(
        store, questions=questions, record_index={RECORD_ID: RECORD, record_id_2: record_2}
    )
    assert len(rows) == 112  # 56 rows x 2 questions
    assert {r.query_id for r in rows} == {"q1", "q2"}
