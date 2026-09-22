"""The 16-arm x alpha x K sweep (UNIFIED-ABLATION-PROPOSAL.md §3, §6;
PRD-112 / ARCH-043).

Reuses, unchanged: `model_ablation.ablation.fetch_corpus`/`Corpus`,
`model_ablation.encoders.get_sapbert_encoder`/`get_medcpt_encoders`,
`retrieval_tuning.sweep.SweepQuestion`/`fetch_calibration_questions`,
`question_gen.deterministic.build_deterministic_narrative`/
`build_present_only_narrative` (Level 1), `orchestration_ablation.ablation
.load_attested_vocabulary`, `orchestration_ablation.augment
.build_arm_c_query`/`load_synthetic_record_index`/`resolve_source_record`
(Level 2), `unified_ablation.blend` (Level 3), `app.eval.metrics.mrr`.

One real BM25 query + one SapBERT encode + one MedCPT encode per (query,
Level-1, Level-2) combination — 4 combinations per query — shared across
that combination's four Level-3 arms and every alpha/k row derived from
them, not recomputed per row.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING

import numpy as np

from app.eval.ablation_config import ALL_ARMS as _ALL_ARMS
from app.eval.ablation_config import AblationArm, alpha_values_for, k_values
from app.eval.auto_seed import _TOPIC
from app.eval.deidentified_source import load_deidentified_records
from app.eval.metrics import mrr
from app.eval.model_ablation.ablation import Corpus, _l2_normalize_rows, fetch_corpus
from app.eval.model_ablation.encoders import Encoder, get_medcpt_encoders, get_sapbert_encoder
from app.eval.orchestration_ablation.augment import (
    build_arm_c_query,
    load_synthetic_record_index,
    resolve_source_record,
)
from app.eval.question_gen.deterministic import (
    build_deterministic_narrative,
    build_present_only_narrative,
)
from app.eval.retrieval_tuning.sweep import SweepQuestion, fetch_calibration_questions
from app.eval.unified_ablation.blend import (
    blend_bm25_dense,
    bm25_raw_scores,
    combine_dense_scores,
    cosine_raw_scores,
)
from app.eval.unified_ablation.per_query import PerQueryResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.records.concepts import ConceptVocabulary
    from app.retrieval.vectorstore import QdrantVectorStore

_LEVEL1_BUILDERS = {
    "present_only": build_present_only_narrative,
    "all_assessed": build_deterministic_narrative,
}


def _first_relevant_rank(retrieved: list[str], gold: set[str]) -> int | None:
    """The actual 1-indexed rank of the first gold hit in the FULL
    (untruncated) ranking — requirement IX's own `first_relevant_rank`
    field, independent of any one k. `reciprocal_rank_at_k` (per row) is
    still computed via `app.eval.metrics.mrr`, reused unchanged, not derived
    from this value, so the two are two independent looks at the same
    ranking rather than one silently trusting the other."""
    for i, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold:
            return i
    return None


def _load_record_index(session: Session, records_dir: str | None) -> dict[uuid.UUID, dict]:
    """De-identified first, synthetic fallback — the same combined
    resolution `app.eval.auto_seed._existing_accepted_records` already
    established (DEVIATIONS.md #188), reused here since a calibration
    question's `source_record_id` can come from either pipeline. Imports
    are module-level here (unlike `app.eval.auto_seed`'s own lazy imports of
    the same functions) — `app.eval.tasks` imports `auto_seed.py` at ITS OWN
    module level, which is what forces `auto_seed.py` to import these
    lazily; nothing imports `unified_ablation` from `app.eval.tasks`, so
    this module isn't part of that cycle (confirmed live, not assumed)."""
    deidentified = dict(load_deidentified_records(session, dataset_id=None))
    synthetic = load_synthetic_record_index(records_dir)
    return {**synthetic, **deidentified}


class _QueryChannelScores:
    """BM25/SapBERT/MedCPT raw scores for one already-built query text —
    computed once, reused by all four Level-3 arms that share this
    (query, Level-1, Level-2) combination's text."""

    __slots__ = ("bm25", "sapbert", "medcpt")

    def __init__(self, bm25: dict[str, float], sapbert: dict[str, float], medcpt: dict[str, float]):
        self.bm25 = bm25
        self.sapbert = sapbert
        self.medcpt = medcpt


def _rank_for_arm(scores: _QueryChannelScores, arm: AblationArm, *, alpha: float) -> list[str]:
    if arm.level3 == "bm25":
        return blend_bm25_dense(scores.bm25, {}, alpha=alpha)
    if arm.level3 == "bm25_sapbert":
        return blend_bm25_dense(scores.bm25, scores.sapbert, alpha=alpha)
    if arm.level3 == "bm25_medcpt":
        return blend_bm25_dense(scores.bm25, scores.medcpt, alpha=alpha)
    if arm.level3 == "bm25_sapbert_medcpt":
        combined = combine_dense_scores(scores.sapbert, scores.medcpt)
        return blend_bm25_dense(scores.bm25, combined, alpha=alpha)
    raise ValueError(f"unknown level3 condition: {arm.level3!r}")  # pragma: no cover


def sweep_questions(
    questions: list[SweepQuestion],
    store: QdrantVectorStore,
    corpus: Corpus,
    *,
    sapbert_encoder: Encoder,
    sapbert_chunk_matrix: np.ndarray,
    medcpt_query_encoder: Encoder,
    medcpt_chunk_matrix: np.ndarray,
    record_index: dict[uuid.UUID, dict],
    vocabulary: ConceptVocabulary | None,
    experiment_id: str,
    k_grid: tuple[int, ...],
) -> Iterator[PerQueryResult]:
    """Pure sweep over already-fetched `questions`/`corpus` — no I/O beyond
    the encoders/`store` callers already hold open, no Postgres session.
    Mirrors `model_ablation.ablation.run_ablation`/`retrieval_tuning.sweep
    .run_sweep`'s own split: fast, offline-testable (`:memory:` Qdrant +
    stub encoders), separate from the thin DB-touching orchestrator
    (`run_unified_ablation`) below.

    `vocabulary` is `None` when `data/clinical_concepts.yaml` isn't
    attested (`orchestration_ablation.ablation.load_attested_vocabulary`,
    reused unchanged) — every Level-2-enriched row then falls back to the
    Level-1 text unchanged, same convention `app.eval.auto_seed`/
    `orchestration_ablation` already use, never a reason to fail the whole
    run.

    A question whose own source record can't be resolved in `record_index`
    (`resolve_source_record` returns `None` — no `source_record_id` at all,
    or one present in neither the de-identified nor the synthetic index) is
    skipped entirely, not evaluated with a guessed/missing record: Level 1's
    whole point is deterministically rebuilding the narrative from the
    record's own fields, so there is nothing to build from without one."""
    for question in questions:
        gold = set(question.gold_chunk_ids)
        record = resolve_source_record(question.source_record_id, record_index)
        if record is None:
            continue

        for level1, builder in _LEVEL1_BUILDERS.items():
            # `topic` is fixed and operator-supplied (DEVIATIONS.md #190/
            # #191) -- the SAME topic for both Level-1 branches, so the only
            # thing that differs between them is present/absent handling,
            # per the comparability requirement (proposal §III).
            base_text = builder(record.model_dump(mode="json"), topic=_TOPIC)

            enriched_text = base_text
            if vocabulary is not None:
                enriched_text = build_arm_c_query(base_text, vocabulary, record).text

            level2_texts = {"raw": base_text, "enriched": enriched_text}

            for level2, query_text in level2_texts.items():
                bm25 = bm25_raw_scores(store, query_text, corpus.chunk_ids)
                sapbert_qvec = sapbert_encoder.encode([query_text])[0]
                medcpt_qvec = medcpt_query_encoder.encode([query_text])[0]
                scores = _QueryChannelScores(
                    bm25=bm25,
                    sapbert=cosine_raw_scores(sapbert_qvec, sapbert_chunk_matrix, corpus.chunk_ids),
                    medcpt=cosine_raw_scores(medcpt_qvec, medcpt_chunk_matrix, corpus.chunk_ids),
                )

                for arm in _ALL_ARMS:
                    if arm.level1 != level1 or arm.level2 != level2:
                        continue
                    for alpha in alpha_values_for(arm):
                        ranking = _rank_for_arm(scores, arm, alpha=alpha)
                        first_rank = _first_relevant_rank(ranking, gold)
                        for k in k_grid:
                            yield PerQueryResult(
                                query_id=question.question_id,
                                patient_id_or_case_id=str(question.source_record_id or ""),
                                experiment_id=experiment_id,
                                level1_condition=level1,
                                level2_condition=level2,
                                level3_condition=arm.level3,
                                k=k,
                                alpha=alpha,
                                query_text=query_text,
                                concept_enriched_query=enriched_text,
                                retrieved_ids=ranking[:k],
                                relevant_ids=sorted(gold),
                                first_relevant_rank=first_rank,
                                reciprocal_rank_at_k=mrr(ranking[:k], gold),
                            )


def run_unified_ablation(
    session: Session,
    store: QdrantVectorStore,
    *,
    experiment_id: str | None = None,
    vocabulary: ConceptVocabulary | None,
    records_dir: str | None = None,
) -> Iterator[PerQueryResult]:
    """Thin orchestrator: fetch questions/corpus/records from the real
    Postgres session + Qdrant store, then delegate to `sweep_questions` (the
    part that's actually testable offline). Yields one `PerQueryResult` per
    (query, arm, alpha, k) row — a generator, not a list, since a real run's
    row count is large (§6) and `per_query.write_per_query_results` streams
    them to disk as they're produced rather than holding the whole run in
    memory."""
    exp_id = experiment_id or str(uuid.uuid4())
    questions: list[SweepQuestion] = fetch_calibration_questions(session)
    corpus: Corpus = fetch_corpus(store)

    sapbert_encoder = get_sapbert_encoder()
    medcpt_query_encoder, medcpt_article_encoder = get_medcpt_encoders()
    sapbert_chunk_matrix = _l2_normalize_rows(
        np.asarray(sapbert_encoder.encode(corpus.texts), dtype=np.float64)
    )
    medcpt_chunk_matrix = _l2_normalize_rows(
        np.asarray(medcpt_article_encoder.encode(corpus.texts), dtype=np.float64)
    )

    # Needed unconditionally for Level 1 (rebuilding the narrative from the
    # record's own fields), not only when `vocabulary` is attested.
    record_index = _load_record_index(session, records_dir)

    yield from sweep_questions(
        questions,
        store,
        corpus,
        sapbert_encoder=sapbert_encoder,
        sapbert_chunk_matrix=sapbert_chunk_matrix,
        medcpt_query_encoder=medcpt_query_encoder,
        medcpt_chunk_matrix=medcpt_chunk_matrix,
        record_index=record_index,
        vocabulary=vocabulary,
        experiment_id=exp_id,
        k_grid=k_values(),
    )
