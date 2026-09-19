"""Runs all three arms (single-stage / criteria-reuse / operator-vocabulary)
of the orchestration ablation over the eval-question pool, scoring against
known gold chunks (PRD-111; PHASE7-PROPOSAL.md §2/§6). Reuses
`app.eval.metrics.precision_recall_at_k`/`mrr` and
`app.retrieval.hybrid.retrieve` unchanged — this module only supplies
alternative *queries* to run through the real retrieval pipeline; it does
not reimplement retrieval or the metrics themselves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.eval import EvalQuestion
from app.eval.metrics import mrr, precision_recall_at_k
from app.eval.orchestration_ablation.augment import (
    build_arm_b_query,
    build_arm_c_query,
    load_synthetic_record_index,
    resolve_source_record,
)
from app.records.concepts import ConceptVocabulary, ConceptVocabularyNotAttested, load_vocabulary
from app.retrieval.hybrid import retrieve
from app.retrieval.vectorstore import VectorStore
from app.schemas.enums import ExpectedOutcome, Provenance

SINGLE_STAGE = "single_stage"
CRITERIA_REUSE = "criteria_reuse"
VOCABULARY = "vocabulary"
CORE_ARMS: tuple[str, ...] = (SINGLE_STAGE, CRITERIA_REUSE)  # always run
ALL_ARMS: tuple[str, ...] = (
    SINGLE_STAGE,
    CRITERIA_REUSE,
    VOCABULARY,
)  # VOCABULARY only if attested

K_VALUES: tuple[int, ...] = (
    5,
    8,
    24,
)  # matches the eval harness's existing reporting set (PHASE7-PROPOSAL.md §6)
MRR_K = 8


@dataclass(frozen=True)
class AblationQuestion:
    question_id: str
    text: str
    gold_chunk_ids: frozenset[str]
    source_record_id: uuid.UUID | None


def fetch_ablation_questions(
    session: Session, *, expected_outcome: str, require_gold: bool
) -> list[AblationQuestion]:
    """Auto-generated questions for one `expected_outcome` slice
    (PHASE7-PROPOSAL.md §3: primary = `well_supported` + non-empty gold,
    `require_gold=True`; secondary = `missing_info_expected`, gold not
    required)."""
    stmt = select(EvalQuestion).where(
        EvalQuestion.expected_outcome == expected_outcome,
        EvalQuestion.provenance == Provenance.AUTO_GENERATED,
    )
    rows = session.execute(stmt).scalars().all()
    out: list[AblationQuestion] = []
    for row in rows:
        if require_gold and not row.gold_relevant_chunks:
            continue
        out.append(
            AblationQuestion(
                question_id=str(row.id),
                text=row.text,
                gold_chunk_ids=frozenset(row.gold_relevant_chunks or []),
                source_record_id=row.source_record_id,
            )
        )
    return out


@dataclass(frozen=True)
class ArmOutcome:
    ranked_chunk_ids: list[str]
    fired: bool
    retrieval_calls: int


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    gold_chunk_ids: frozenset[str]
    arms: dict[str, ArmOutcome] = field(default_factory=dict)


def run_question(
    question: AblationQuestion,
    *,
    vectorstore: VectorStore,
    record_index: dict[uuid.UUID, dict],
    vocabulary: ConceptVocabulary | None,
) -> QuestionResult:
    """Runs Arm A + Arm B always; Arm C only if `vocabulary` is not `None`
    (the caller's signal that `data/clinical_concepts.yaml` is attested —
    PHASE7-PROPOSAL.md §9: an unattested vocabulary means Arm C is skipped
    for the whole run, not silently faked per-question)."""
    record = resolve_source_record(question.source_record_id, record_index)

    pass1_items, _ = retrieve(question.text, vectorstore=vectorstore)
    pass1_ranked = [item["chunk_id"] for item in pass1_items]
    arms: dict[str, ArmOutcome] = {
        SINGLE_STAGE: ArmOutcome(ranked_chunk_ids=pass1_ranked, fired=False, retrieval_calls=1)
    }

    arm_b_query = build_arm_b_query(question.text, pass1_items, record)
    if arm_b_query.fired:
        pass2_items, _ = retrieve(arm_b_query.text, vectorstore=vectorstore)
        arms[CRITERIA_REUSE] = ArmOutcome(
            ranked_chunk_ids=[item["chunk_id"] for item in pass2_items],
            fired=True,
            retrieval_calls=2,
        )
    else:
        # Nothing to reuse -- Arm B == Arm A for this question, no second
        # retrieval call made (PHASE7-PROPOSAL.md §2 step 4).
        arms[CRITERIA_REUSE] = ArmOutcome(
            ranked_chunk_ids=pass1_ranked, fired=False, retrieval_calls=1
        )

    if vocabulary is not None:
        arm_c_query = build_arm_c_query(question.text, vocabulary, record)
        if arm_c_query.fired:
            arm_c_items, _ = retrieve(arm_c_query.text, vectorstore=vectorstore)
            arms[VOCABULARY] = ArmOutcome(
                ranked_chunk_ids=[item["chunk_id"] for item in arm_c_items],
                fired=True,
                retrieval_calls=1,
            )
        else:
            arms[VOCABULARY] = ArmOutcome(
                ranked_chunk_ids=pass1_ranked, fired=False, retrieval_calls=1
            )

    return QuestionResult(
        question_id=question.question_id, gold_chunk_ids=question.gold_chunk_ids, arms=arms
    )


@dataclass(frozen=True)
class SliceReport:
    slice_name: str
    n_questions: int
    arms_present: tuple[str, ...]
    # each row: {"arm": str, "k": int, "recall": float}
    recall_rows: list[dict]
    # each row: {"arm": str, "mrr": float}
    mrr_rows: list[dict]
    fired_rate: dict[str, float]  # arm -> fraction of questions where that arm differed from Arm A
    avg_retrieval_calls: dict[str, float]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(slice_name: str, results: list[QuestionResult]) -> SliceReport:
    """Pure aggregation over already-computed per-question results — no I/O,
    so this is the piece exercised by a small, fast offline unit test
    independent of `run_question`'s Qdrant/embedding/DB calls (same split as
    `app.eval.retrieval_tuning.sweep.run_sweep`)."""
    arms_present = (
        tuple(a for a in ALL_ARMS if all(a in r.arms for r in results)) if results else ()
    )

    recall_rows: list[dict] = []
    mrr_rows: list[dict] = []
    fired_rate: dict[str, float] = {}
    avg_retrieval_calls: dict[str, float] = {}

    for arm in arms_present:
        for k in K_VALUES:
            recalls = [
                precision_recall_at_k(r.arms[arm].ranked_chunk_ids, set(r.gold_chunk_ids), k)[1]
                for r in results
            ]
            recall_rows.append({"arm": arm, "k": k, "recall": _mean(recalls)})
        mrr_scores = [
            mrr(r.arms[arm].ranked_chunk_ids[:MRR_K], set(r.gold_chunk_ids)) for r in results
        ]
        mrr_rows.append({"arm": arm, "mrr": _mean(mrr_scores)})
        if arm != SINGLE_STAGE:
            fired_rate[arm] = _mean([1.0 if r.arms[arm].fired else 0.0 for r in results])
        avg_retrieval_calls[arm] = _mean([float(r.arms[arm].retrieval_calls) for r in results])

    return SliceReport(
        slice_name=slice_name,
        n_questions=len(results),
        arms_present=arms_present,
        recall_rows=recall_rows,
        mrr_rows=mrr_rows,
        fired_rate=fired_rate,
        avg_retrieval_calls=avg_retrieval_calls,
    )


@dataclass(frozen=True)
class FullAblationResult:
    well_supported: SliceReport
    missing_info: SliceReport
    vocabulary_attested: bool
    vocabulary_error: str | None


def load_attested_vocabulary(path: str | Path) -> tuple[ConceptVocabulary | None, str | None]:
    """`(vocabulary, None)` if `path` is fully attested; `(None, message)`
    otherwise — Arm C is skipped for the whole run, never run against a
    placeholder (PHASE7-PROPOSAL.md §4/§9)."""
    try:
        return load_vocabulary(path), None
    except (ConceptVocabularyNotAttested, FileNotFoundError) as exc:
        return None, str(exc)


def run_full_ablation(
    session: Session,
    vectorstore: VectorStore,
    *,
    records_dir: str | None = None,
    concepts_path: str | Path,
) -> FullAblationResult:
    """Runs both slices (`well_supported` primary, `missing_info_expected`
    secondary) across all attested arms (PHASE7-PROPOSAL.md §3/§6)."""
    record_index = load_synthetic_record_index(records_dir)
    vocabulary, vocab_error = load_attested_vocabulary(concepts_path)

    def _run_slice(slice_name: str, *, require_gold: bool) -> SliceReport:
        questions = fetch_ablation_questions(
            session, expected_outcome=slice_name, require_gold=require_gold
        )
        results = [
            run_question(
                q, vectorstore=vectorstore, record_index=record_index, vocabulary=vocabulary
            )
            for q in questions
        ]
        return aggregate(slice_name, results)

    well_supported = _run_slice(ExpectedOutcome.WELL_SUPPORTED, require_gold=True)
    missing_info = _run_slice(ExpectedOutcome.MISSING_INFO_EXPECTED, require_gold=False)

    return FullAblationResult(
        well_supported=well_supported,
        missing_info=missing_info,
        vocabulary_attested=vocabulary is not None,
        vocabulary_error=vocab_error,
    )
