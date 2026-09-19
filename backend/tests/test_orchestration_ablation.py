"""Phase 7 orchestration-ablation tooling (PRD-111), run against
qdrant-client's embedded in-memory mode with the offline stub embedding
backend — no network, no real models, no real Postgres (CLAUDE.md §5).
Mirrors `tests/test_retrieval_tuning.py`'s fixture pattern.

`fetch_ablation_questions`/`run_full_ablation` (plain SQLAlchemy queries
against `eval.eval_question`) are not covered here — they need a real
Postgres for a meaningful test, same precedent as
`app.eval.retrieval_tuning.sweep.fetch_calibration_questions`
(`test_retrieval_tuning.py`'s own module docstring)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import yaml

from app.config import get_settings
from app.eval.orchestration_ablation.ablation import (
    CRITERIA_REUSE,
    SINGLE_STAGE,
    VOCABULARY,
    AblationQuestion,
    ArmOutcome,
    QuestionResult,
    aggregate,
    load_attested_vocabulary,
    run_question,
)
from app.eval.orchestration_ablation.augment import (
    build_arm_b_query,
    build_arm_c_query,
    load_synthetic_record_index,
    resolve_source_record,
)
from app.eval.tasks import _RECORD_ID_NAMESPACE
from app.records.concepts import Concept, ConceptVocabulary
from app.retrieval.vectorstore import QdrantVectorStore
from app.schemas.record import PatientRecord
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
    s = QdrantVectorStore(url=":memory:", api_key="", collection="orchestration_ablation_test")
    s.ensure_collection(dense_dim=_DENSE_DIM)
    return s


_RECORD_ID = "test-rec-1"
_RECORD_UUID = uuid.uuid5(_RECORD_ID_NAMESPACE, _RECORD_ID)
_RECORD_DICT = {
    "schema_version": "1.4.0",
    "dataset_provenance": "synthetic-generator-v1",
    "record_id": _RECORD_ID,
    "mrn": "SYN-TEST-1",
    "vitals": [{"resp_rate_bpm": 65.0}],
}


@pytest.fixture
def synthetic_records_dir(tmp_path: Path) -> Path:
    d = tmp_path / "synthetic"
    d.mkdir()
    (d / "patients.json").write_text(json.dumps({"records": [_RECORD_DICT]}), encoding="utf-8")
    return tmp_path


_ATTESTED_VOCAB = {
    "authored_by": "unit-test fixture",
    "authored_date": "2026-09-19",
    "concepts": {
        "fake_tachypnoea": {
            "field": "vitals.resp_rate_bpm",
            "operator": ">",
            "value": 60,
            "source": "unit-test fixture, not a real clinical value",
            "synonyms": ["fake fast breathing"],
        }
    },
}


@pytest.fixture
def vocabulary() -> ConceptVocabulary:
    return ConceptVocabulary(
        authored_by="unit-test fixture",
        authored_date="2026-09-19",
        concepts=tuple(
            Concept(
                name=name,
                field=spec["field"],
                operator=spec["operator"],
                value=float(spec["value"]),
                source=spec["source"],
                synonyms=tuple(spec.get("synonyms") or ()),
            )
            for name, spec in _ATTESTED_VOCAB["concepts"].items()
        ),
    )


# ── load_synthetic_record_index / resolve_source_record ─────────────────────


def test_load_synthetic_record_index_resolves_by_record_id_hash(
    synthetic_records_dir: Path,
) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    assert _RECORD_UUID in index
    record = resolve_source_record(_RECORD_UUID, index)
    assert isinstance(record, PatientRecord)
    assert record.record_id == _RECORD_ID
    assert record.vitals[0].resp_rate_bpm == 65.0


def test_resolve_source_record_none_for_unresolvable_id(synthetic_records_dir: Path) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    assert resolve_source_record(uuid.uuid4(), index) is None


def test_resolve_source_record_none_when_no_source_record_id(synthetic_records_dir: Path) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    assert resolve_source_record(None, index) is None


# ── build_arm_b_query (criteria-reuse) ───────────────────────────────────────

_CRITERIA_CHUNK = {
    "chunk_type": "criteria",
    "meta": {"criteria": [{"field": "respiratory rate", "operator": ">", "value": 60.0}]},
}
_PROSE_CHUNK = {"chunk_type": "prose", "meta": {}}


def test_build_arm_b_query_fires_on_matched_retrieved_criterion(
    synthetic_records_dir: Path,
) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    record = resolve_source_record(_RECORD_UUID, index)
    result = build_arm_b_query("what does the guideline say?", [_CRITERIA_CHUNK], record)
    assert result.fired is True
    assert "respiratory rate" in result.text
    assert "60.0" in result.text


def test_build_arm_b_query_no_fire_when_criterion_not_matched(synthetic_records_dir: Path) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    record = resolve_source_record(_RECORD_UUID, index)
    unmatched = {
        "chunk_type": "criteria",
        "meta": {"criteria": [{"field": "respiratory rate", "operator": ">", "value": 999.0}]},
    }
    result = build_arm_b_query("q", [unmatched], record)
    assert result.fired is False
    assert result.text == "q"


def test_build_arm_b_query_no_fire_without_criteria_chunks() -> None:
    record = PatientRecord(
        record_id="x", mrn="y"
    )  # a real record, just no criteria chunk in pass 1
    result = build_arm_b_query("q", [_PROSE_CHUNK], record)
    assert result.fired is False


def test_build_arm_b_query_no_fire_without_record() -> None:
    result = build_arm_b_query("q", [_CRITERIA_CHUNK], None)
    assert result.fired is False
    assert result.text == "q"


# ── build_arm_c_query (operator-vocabulary) ──────────────────────────────────


def test_build_arm_c_query_fires_and_appends_synonym(
    synthetic_records_dir: Path, vocabulary: ConceptVocabulary
) -> None:
    index = load_synthetic_record_index(str(synthetic_records_dir))
    record = resolve_source_record(_RECORD_UUID, index)
    result = build_arm_c_query("q", vocabulary, record)
    assert result.fired is True
    assert "fake_tachypnoea (fake fast breathing)" in result.text


def test_build_arm_c_query_no_fire_without_record(vocabulary: ConceptVocabulary) -> None:
    result = build_arm_c_query("q", vocabulary, None)
    assert result.fired is False
    assert result.text == "q"


# ── load_attested_vocabulary ─────────────────────────────────────────────────


def test_load_attested_vocabulary_ok(tmp_path: Path) -> None:
    p = tmp_path / "concepts.yaml"
    p.write_text(yaml.safe_dump(_ATTESTED_VOCAB), encoding="utf-8")
    vocab, err = load_attested_vocabulary(p)
    assert err is None
    assert vocab is not None


def test_load_attested_vocabulary_none_on_placeholder(tmp_path: Path) -> None:
    p = tmp_path / "concepts.yaml"
    p.write_text(
        yaml.safe_dump({"authored_by": "TODO_CONFIRM", "authored_date": "x"}), encoding="utf-8"
    )
    vocab, err = load_attested_vocabulary(p)
    assert vocab is None
    assert err is not None


def test_load_attested_vocabulary_none_on_missing_file(tmp_path: Path) -> None:
    vocab, err = load_attested_vocabulary(tmp_path / "does-not-exist.yaml")
    assert vocab is None
    assert err is not None


# ── run_question (real :memory: Qdrant, stub embeddings) ────────────────────


def test_run_question_all_three_arms_offline(
    store: QdrantVectorStore, synthetic_records_dir: Path, vocabulary: ConceptVocabulary
) -> None:
    target_text = "Neonates with respiratory rate above 60 breaths per minute are tachypnoeic."
    _seed_chunk(store, 1, chunk_id="c1", text=target_text, **_CRITERIA_CHUNK)
    _seed_chunk(store, 2, chunk_id="c2", text="Vitamin K is given to newborns shortly after birth.")

    index = load_synthetic_record_index(str(synthetic_records_dir))
    question = AblationQuestion(
        question_id="q1",
        text="What does the guideline recommend for a neonate with fast breathing?",
        gold_chunk_ids=frozenset({"c1"}),
        source_record_id=_RECORD_UUID,
    )
    result = run_question(question, vectorstore=store, record_index=index, vocabulary=vocabulary)

    assert set(result.arms) == {SINGLE_STAGE, CRITERIA_REUSE, VOCABULARY}
    assert result.arms[SINGLE_STAGE].retrieval_calls == 1
    assert result.arms[CRITERIA_REUSE].fired is True
    assert result.arms[CRITERIA_REUSE].retrieval_calls == 2
    assert result.arms[VOCABULARY].fired is True
    assert result.arms[VOCABULARY].retrieval_calls == 1
    for outcome in result.arms.values():
        assert "c1" in outcome.ranked_chunk_ids or "c2" in outcome.ranked_chunk_ids


def test_run_question_vocabulary_arm_absent_when_not_attested(
    store: QdrantVectorStore, synthetic_records_dir: Path
) -> None:
    _seed_chunk(store, 1, chunk_id="c1", text="Vitamin K is given to newborns.")
    index = load_synthetic_record_index(str(synthetic_records_dir))
    question = AblationQuestion(
        question_id="q1", text="q", gold_chunk_ids=frozenset(), source_record_id=None
    )
    result = run_question(question, vectorstore=store, record_index=index, vocabulary=None)
    assert VOCABULARY not in result.arms
    assert set(result.arms) == {SINGLE_STAGE, CRITERIA_REUSE}


# ── aggregate (pure) ──────────────────────────────────────────────────────────


def _outcome(ids: list[str], *, fired: bool, calls: int) -> ArmOutcome:
    return ArmOutcome(ranked_chunk_ids=ids, fired=fired, retrieval_calls=calls)


def test_aggregate_computes_recall_mrr_fired_rate_and_avg_calls() -> None:
    results = [
        QuestionResult(
            question_id="q1",
            gold_chunk_ids=frozenset({"gold1"}),
            arms={
                SINGLE_STAGE: _outcome(["other", "gold1"], fired=False, calls=1),
                CRITERIA_REUSE: _outcome(["gold1"], fired=True, calls=2),
            },
        ),
        QuestionResult(
            question_id="q2",
            gold_chunk_ids=frozenset({"gold2"}),
            arms={
                SINGLE_STAGE: _outcome(["nope"], fired=False, calls=1),
                CRITERIA_REUSE: _outcome(["nope"], fired=False, calls=1),
            },
        ),
    ]
    report = aggregate("well_supported", results)

    assert report.n_questions == 2
    assert set(report.arms_present) == {SINGLE_STAGE, CRITERIA_REUSE}
    # single_stage: q1 gold at rank 2 -> mrr 0.5; q2 miss -> 0.0; mean 0.25
    single_stage_mrr = next(r["mrr"] for r in report.mrr_rows if r["arm"] == SINGLE_STAGE)
    assert single_stage_mrr == pytest.approx(0.25)
    # criteria_reuse: q1 gold at rank 1 -> mrr 1.0; q2 miss -> 0.0; mean 0.5
    criteria_mrr = next(r["mrr"] for r in report.mrr_rows if r["arm"] == CRITERIA_REUSE)
    assert criteria_mrr == pytest.approx(0.5)
    assert report.fired_rate[CRITERIA_REUSE] == pytest.approx(0.5)  # fired on q1 only
    assert report.avg_retrieval_calls[SINGLE_STAGE] == pytest.approx(1.0)
    assert report.avg_retrieval_calls[CRITERIA_REUSE] == pytest.approx(1.5)


def test_aggregate_empty_results_is_empty_report() -> None:
    report = aggregate("well_supported", [])
    assert report.n_questions == 0
    assert report.arms_present == ()
    assert report.recall_rows == []


def test_aggregate_excludes_vocabulary_arm_when_absent_from_any_result() -> None:
    results = [
        QuestionResult(
            question_id="q1",
            gold_chunk_ids=frozenset({"g"}),
            arms={
                SINGLE_STAGE: _outcome(["g"], fired=False, calls=1),
                CRITERIA_REUSE: _outcome(["g"], fired=False, calls=1),
            },
        )
    ]
    report = aggregate("well_supported", results)
    assert VOCABULARY not in report.arms_present
