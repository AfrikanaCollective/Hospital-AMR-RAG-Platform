"""Auto-seed the rubric review queue from de-identified records
(ARCH §14.2, §15; DEVIATIONS.md #113).

Wires together, end to end:
1. `app.eval.deidentified_source.load_deidentified_records` — already-ingested
   de-identified patient records (never synthetic ones — this pipeline is
   specifically "from the existing de-identified anonymised patient-level
   records").
2. `app.eval.question_gen` — a 60/20/20 `expected_outcome`-stratified plan
   of unique narrative questions, with the diversity filter (ARCH §15.1
   step 7, `app.eval.question_gen.diversity`) enforced. Narrative
   construction is deterministic (`app.eval.question_gen.deterministic
   .build_deterministic_narrative`, DEVIATIONS.md #190 — was the LLM-based
   `generate.py::generate_question`), built only from the record's own
   field values, no fabrication risk, no validator/retry step.
3. The real query pipeline (`app.agents.graph_runtime.invoke_graph`, the
   SAME code path `/query` uses) for each generated question.
4. Persist an `eval.Result` row with `queue_state='open'` **immediately** —
   not `'not_queued'`. Before this module, nothing anywhere in this codebase
   ever wrote an `eval.Result` row (confirmed: `git grep` for `Result(` in
   `app/` before this change matches only the model definition itself) — the
   rubric workflow's own `queue_state` transition
   (`app.rubric.workflow.submit_rating`, `not_queued -> open` on first
   rating) assumed a result already existed *before* any rating, which
   nothing produced. This is the piece that makes "the queue is already full
   when a reviewer logs in" true.

Idempotent: counts auto-generated `eval_question` rows that already have a
`Result` (this pipeline's own output — the harness's *separate*
`app.eval.tasks.generate_questions`, which seeds the fixed synthetic test
set, produces `eval_question` rows with no `Result` and is never counted
here) and only tops up to `target_count`. A container restart does not
duplicate the queue.

**One scenario per record, durably (DEVIATIONS.md #114):** every patient id
already used as `EvalQuestion.source_record_id` by a prior auto-generated
question — across *all* previous runs, not just this one — is excluded from
the candidate pool before generation starts (`_used_patient_ids`), and a
record picked successfully within this run is excluded from the rest of
this run too (`used_this_run`). A given de-identified record can never
source more than one queued scenario.

**Diversity across runs, not just within one (DEVIATIONS.md #114):** the
near-duplicate filter's `accepted_records` seed is every already-accepted
auto-generated question's own SOURCE RECORD (re-resolved by
`_existing_accepted_records`, DEVIATIONS.md #188 — not an embedding; see
`app.eval.question_gen.diversity`'s module docstring for why an
embedding-based check was tried twice and replaced) — not an empty list —
so a later top-up run (e.g. raising `QGEN_AUTO_SEED_COUNT`) cannot re-accept
a clinically near-duplicate record of one already queued in an earlier run.

**Commits per scenario, not once for the whole run (DEVIATIONS.md #115):**
each `_generate_one_scenario` call commits immediately on success, rather
than the caller committing once after all `target_count` scenarios are
done. `target_count=100` against a real gateway is real minutes of real LLM
calls; without this, nothing would be visible to a reviewer, a health
check, or a direct `psql` query until the *entire* run finished, and a
crash or an unhandled error near the end would discard every
already-generated scenario instead of keeping what had already succeeded —
found live, running this against a real Postgres + real gateway for the
first time (the offline test suite's `_FakeSession` doesn't model
transactions, so it couldn't have caught this).

**Transient gateway errors skip one attempt, not the whole run
(DEVIATIONS.md #116):** a timeout or a 503 from the real gateway, during
either narrative generation or the real pipeline invocation, is caught and
logged rather than left to crash the Celery task — found live, the hard
way: after #115's own live-verification session ended, one such error went
uncaught, crashed `auto_seed_review_queue_task`, and — since nothing
reschedules or retries it — generation simply stalled at 17/100 for about
12 hours until this fix landed and the API was restarted. Every real
network call (generation, embedding, the pipeline) now happens *before*
anything is added to the session, so a caught transient failure never
leaves a half-written `EvalQuestion` pending for a later commit to
accidentally sweep in.

**Multi-stage audit fields (DEVIATIONS.md #186), per direct operator
request**: each scenario's `Result` also carries a read-only, never-rated
"multi-stage" counterpart — the same question text run through Phase 7's
operator-vocabulary query augmentation (`app.eval.orchestration_ablation
.augment.build_arm_c_query`, reused unchanged; PRD-111 Arm C), for
audit/comparison purposes only. When augmentation doesn't fire for a given
record (no concept matched — the common case; DEVIATIONS #154 found this
fires on only ~2.9% of well_supported de-identified-sourced questions), the
multi-stage query is recorded as identical to the single-stage one and no
second pipeline invocation is made (`multi_stage_fired=False`, no extra
LLM-gateway cost). When it does fire, the augmented text is run through the
*same* real pipeline a second time and its full answer/citations/grounding
report are persisted alongside the single-stage ones — the reviewer still
rates only the single-stage answer; nothing about the rating workflow
changes.
"""

from __future__ import annotations

import json
import random
import uuid
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import func, select

from app.config import get_settings
from app.crypto.provider import get_crypto
from app.db.models.eval import (
    EvalQuestion,
    Result,
    result_answer_aad,
    result_multi_stage_answer_aad,
    result_segments_aad,
)
from app.eval.deidentified_source import load_deidentified_records

# NOT imported at module level: `app.eval.orchestration_ablation.augment`
# imports back from `app.eval.tasks`, which imports `run_auto_seed_review_queue`
# from *this* module at ITS OWN module level -- a module-level import here
# would be a real circular import (confirmed live: `ImportError: cannot
# import name '_RECORD_ID_NAMESPACE' from partially initialized module
# 'app.eval.tasks'`), not a hypothetical one. `load_attested_vocabulary`/
# `build_arm_c_query`/`load_synthetic_record_index` are imported lazily
# inside the functions that use them instead -- same rationale/pattern as
# this module's own existing lazy `app.agents.graph_runtime` import in
# `_invoke_pipeline` below.
from app.eval.question_gen.deterministic import build_deterministic_narrative
from app.eval.question_gen.diversity import is_clinically_near_duplicate
from app.eval.question_gen.planner import Composition, allocate
from app.llm.gateway import LLMGatewayError
from app.logging import get_logger
from app.records.concepts import ConceptVocabulary
from app.schemas.citation import Citation
from app.schemas.enums import ExpectedOutcome, ObservedOutcome, Provenance
from app.schemas.query import AnswerSegment
from app.schemas.record import PatientRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.eval.orchestration_ablation.augment import AugmentedQuery

logger = get_logger(__name__)

_LOAD_RECORDS_FN = load_deidentified_records

# Default operator-attested vocabulary path for the multi-stage audit fields
# (DEVIATIONS.md #186) — same default/env-override convention as
# `scripts/run_orchestration_ablation.py`/`scripts/run_model_ablation.py`.
_DEFAULT_CONCEPTS_PATH = "data/clinical_concepts.yaml"

# Operator-supplied topic (DEVIATIONS.md #191, correcting #190's own generic
# placeholder "this newborn's presentation"): `build_deterministic_narrative`
# requires an explicit `topic` per its own docstring — real automatic
# topic-matching (ARCH §15.1 step 2, "pick a source record matched to a
# guideline's applicability") remains deferred (DEVIATIONS #67), and
# DEVIATIONS #156's own design note is explicit that topic supply is the
# operator's call, not something this module derives. Matches the scope
# `data/excerpt_guidelines/` is actually curated for (antibiotic use,
# neonatal infection management). The actual guideline MATCH still comes
# from the full narrative's real clinical content (findings/vitals/
# problems), not this topic clause — it only frames the question's opening
# line.
_TOPIC = "antibiotics or infection in hospital settings for this newborn's presentation"


def _load_attested_vocabulary(path: str) -> tuple[ConceptVocabulary | None, str | None]:
    # Lazy import -- see module docstring on the circular import through
    # app.eval.tasks a module-level import here would hit. Wrapped in its
    # own module-level function (rather than importing lazily inline at each
    # call site) so it's a monkeypatchable seam, same pattern as
    # `_LOAD_RECORDS_FN`/`_INVOKE_PIPELINE_FN` below -- tests
    # default this to "no vocabulary" (DEVIATIONS.md #186) so they stay
    # deterministic regardless of whether `data/clinical_concepts.yaml`
    # happens to exist and be attested in the environment running them.
    from app.eval.orchestration_ablation.ablation import load_attested_vocabulary  # noqa: PLC0415

    return load_attested_vocabulary(path)


_LOAD_ATTESTED_VOCABULARY_FN = _load_attested_vocabulary


def _build_arm_c_query(
    question_text: str, vocabulary: ConceptVocabulary, record: PatientRecord
) -> AugmentedQuery:
    # Lazy import -- same circular-import reason as `_load_attested_vocabulary`
    # above; wrapped the same way so it's an independently monkeypatchable
    # seam for tests that want to control fired/not-fired without a fully
    # realistic PatientRecord fixture.
    from app.eval.orchestration_ablation.augment import build_arm_c_query  # noqa: PLC0415

    return build_arm_c_query(question_text, vocabulary, record)


_BUILD_ARM_C_QUERY_FN = _build_arm_c_query

# Bounded scan through the shuffled record pool per expected-outcome slot:
# generation failures (QuestionGenerationFailed) and diversity-filter
# rejections both consume an attempt without filling a slot, so the pool is
# scanned more than once if needed, but not unboundedly.
_ATTEMPTS_PER_SLOT_MULTIPLIER = 4
_MIN_ATTEMPTS_PER_SLOT = 6


def _count_existing_auto_seeded(session: Session) -> int:
    stmt = (
        select(func.count())
        .select_from(EvalQuestion)
        .join(Result, Result.eval_question_id == EvalQuestion.id)
        .where(EvalQuestion.provenance == Provenance.AUTO_GENERATED.value)
    )
    return session.execute(stmt).scalar_one()


_COUNT_EXISTING_AUTO_SEEDED_FN = _count_existing_auto_seeded


def _used_patient_ids(session: Session) -> set[uuid.UUID]:
    """Every patient id already used as the source of an auto-generated
    question, from any run (DEVIATIONS.md #114) — not scoped to rows with a
    `Result` the way `_count_existing_auto_seeded` is, since a record that
    produced a question which then failed to reach `Result` (none of this
    module's own code paths leave that gap, but a future caller's might)
    should still count as spent, not be offered again."""
    stmt = select(EvalQuestion.source_record_id).where(
        EvalQuestion.provenance == Provenance.AUTO_GENERATED.value
    )
    return {pid for pid in session.execute(stmt).scalars().all() if pid is not None}


_USED_PATIENT_IDS_FN = _used_patient_ids


def _existing_accepted_records(session: Session) -> list[dict]:
    """Source record dict of every already-accepted auto-generated
    question, re-resolved from its `source_record_id` (DEVIATIONS.md #188)
    — seeds the diversity filter so a later top-up run cannot re-accept a
    clinically near-duplicate record of one already queued. Replaces the
    prior embedding-based version (`_existing_accepted_embeddings`,
    DEVIATIONS #114/#119): see `app.eval.question_gen.diversity`'s module
    docstring for why two embedding-based attempts were tried and both
    failed live.

    Resolves each `source_record_id` two ways, matching how it could have
    been sourced: de-identified (`app.eval.auto_seed`'s own only writer, the
    vast majority) via `load_deidentified_records`, or synthetic (the
    deterministic-question-generator path, DEVIATIONS #156-158) via
    `load_synthetic_record_index`. A row resolving via neither (shouldn't
    happen — every `auto_generated` row with a `source_record_id` came from
    one of these two paths) is simply skipped, not treated as an error —
    same "disclosed, non-silent gap" precedent as the embedding version's
    own skip conditions had."""
    # Lazy import -- see this module's docstring on the circular import
    # through app.eval.tasks a module-level import here would hit.
    from app.eval.orchestration_ablation.augment import load_synthetic_record_index  # noqa: PLC0415

    stmt = select(EvalQuestion.source_record_id).where(
        EvalQuestion.provenance == Provenance.AUTO_GENERATED.value,
        EvalQuestion.source_record_id.is_not(None),
    )
    source_record_ids = {sid for sid in session.execute(stmt).scalars().all() if sid is not None}
    if not source_record_ids:
        return []

    deidentified = dict(_LOAD_RECORDS_FN(session, dataset_id=None))
    synthetic = load_synthetic_record_index()
    return [
        record
        for sid in source_record_ids
        if (record := deidentified.get(sid) or synthetic.get(sid)) is not None
    ]


_EXISTING_RECORDS_FN = _existing_accepted_records


class _GenerationState:
    """Mutable state threaded through one `run_auto_seed_review_queue` call
    (DEVIATIONS.md #114): the shuffled candidate pool + cursor, the
    within-run record-reuse guard, and the diversity filter's accepted
    records — seeded from every prior run's output, not just this one."""

    def __init__(
        self,
        records: list[tuple[uuid.UUID, dict]],
        *,
        seed: int | None,
        existing_records: list[dict],
    ) -> None:
        self.shuffled = records[:]
        random.Random(seed).shuffle(self.shuffled)
        self.cursor = 0
        self.used_this_run: set[uuid.UUID] = set()
        self.accepted_records: list[dict] = list(existing_records)

    def next_candidate(self) -> tuple[uuid.UUID, dict] | None:
        """Advances the cursor and returns the next record to try, or `None`
        if it's already sourced a scenario this run — reachable once the
        cursor has cycled the whole pool (a small pool relative to the
        remaining target)."""
        patient_id, record = self.shuffled[self.cursor % len(self.shuffled)]
        self.cursor += 1
        if patient_id in self.used_this_run:
            return None
        return patient_id, record


def _generate_one_scenario(
    session: Session,
    state: _GenerationState,
    expected_outcome: ExpectedOutcome,
    *,
    dedup_threshold: float,
    vocabulary: ConceptVocabulary | None,
) -> uuid.UUID | None:
    """One attempt: pick a candidate record, build the narrative
    deterministically (DEVIATIONS.md #190), reject a near-duplicate, run the
    real pipeline, persist `EvalQuestion` + `Result`, and commit
    (DEVIATIONS.md #115) — returns the new `Result.id`, or `None` for any
    rejection (already used this run, near-duplicate, or a transient
    gateway error on the real pipeline call — DEVIATIONS.md #116) — the
    caller retries with the next candidate, not this function.

    The real graph invocation happens *before* anything is added to
    `session` — found live (DEVIATIONS.md #116): a transient gateway
    failure (a timeout, a 503) during the graph invocation, uncaught,
    crashed the whole Celery task outright, and since nothing auto-retries
    or reschedules it, a single blip silently stalled generation until the
    next container restart — observed stalled for ~12 hours in exactly this
    way. Ordering the real pipeline call before any DB write also means a
    transient failure never leaves a half-written `EvalQuestion` with no
    matching `Result` sitting pending in the session for a later commit to
    pick up by accident."""
    candidate = state.next_candidate()
    if candidate is None:
        return None
    patient_id, record = candidate
    # DEVIATIONS.md #190: deterministic, LLM-free narrative construction
    # (`app.eval.question_gen.deterministic`, DEVIATIONS #156) — was
    # `generate_question` (an LLM call + no-fabrication validator + retry
    # loop). Built entirely from `record`'s own field values, so there is
    # nothing to fabricate and nothing that can fail generation for this
    # record (no `QuestionGenerationFailed`/transient-gateway case here
    # anymore — one real network call fewer per attempt than before).
    text = build_deterministic_narrative(record, topic=_TOPIC)
    # Matches `generate.py`'s own convention (never a topic ref for
    # no_guideline_expected -- there is no real guideline to reference by
    # definition for that slot).
    target_guideline_ref = (
        {"topic": _TOPIC} if expected_outcome != ExpectedOutcome.NO_GUIDELINE_EXPECTED else None
    )

    # DEVIATIONS.md #188: compares the record's own structured clinical
    # fields directly (Jaccard on findings/problems + vitals tolerance) —
    # not an embedding of any kind. See `app.eval.question_gen.diversity`'s
    # module docstring for why two embedding-based attempts (#187) were
    # tried and both failed live.
    if is_clinically_near_duplicate(
        record, state.accepted_records, findings_jaccard_threshold=dedup_threshold
    ):
        return None

    try:
        out = _INVOKE_PIPELINE_FN(text)
    except (httpx.HTTPError, LLMGatewayError) as exc:
        logger.warning(
            "auto_seed_review_queue: transient gateway error running the pipeline for "
            "record %r, skipping this attempt: %s",
            patient_id,
            exc,
        )
        return None

    state.accepted_records.append(record)
    state.used_this_run.add(patient_id)

    # Multi-stage audit fields (DEVIATIONS.md #186) — Phase 7's
    # operator-vocabulary query augmentation, reused unchanged, against this
    # SAME record already in scope for the narrative above (no new PHI/
    # de-identified-data boundary crossed). Pure Python, no network call, so
    # computing `augmented` costs nothing even when the augmentation doesn't
    # fire -- the second real pipeline invocation only happens when it
    # actually produces a different query. `multi_stage_query` stays `None`
    # when `vocabulary` itself is `None` (unattested for the whole run) --
    # deliberately distinct from a computed-but-identical string, so a
    # reader can tell "not computed this run" apart from "computed, this
    # record just didn't match anything."
    multi_stage_query: str | None = None
    multi_stage_fired = False
    multi_stage_out: dict | None = None
    if vocabulary is not None:
        augmented = _BUILD_ARM_C_QUERY_FN(text, vocabulary, PatientRecord.model_validate(record))
        multi_stage_query = augmented.text
        multi_stage_fired = augmented.fired
        if augmented.fired:
            try:
                multi_stage_out = _INVOKE_PIPELINE_FN(augmented.text)
            except (httpx.HTTPError, LLMGatewayError) as exc:
                # Best-effort: the single-stage result above is already
                # complete and valid on its own -- a transient gateway error
                # on the audit-only multi-stage side channel degrades to "no
                # multi-stage answer for this item" rather than discarding
                # the whole scenario (which would waste the narrative
                # generation + embedding + single-stage pipeline call already
                # made). `multi_stage_query`/`multi_stage_fired` are still
                # recorded truthfully -- the augmentation DID produce a
                # different query, the run of it just failed this time.
                logger.warning(
                    "auto_seed_review_queue: transient gateway error running the multi-stage "
                    "(vocabulary-augmented) pipeline for record %r -- keeping the single-stage "
                    "result, multi-stage answer left empty for this item: %s",
                    patient_id,
                    exc,
                )

    question = EvalQuestion(
        text=text,
        provenance=Provenance.AUTO_GENERATED,
        expected_outcome=expected_outcome,
        source_record_id=patient_id,
        target_guideline_ref=target_guideline_ref,
        generator_meta={"template_version": "deterministic-v1"},
        in_fixed_testset=False,
    )
    session.add(question)
    session.flush()

    result, answer_text, segment_dicts, multi_stage_answer_text = _build_result(
        question,
        out,
        multi_stage_query=multi_stage_query,
        multi_stage_fired=multi_stage_fired,
        multi_stage_out=multi_stage_out,
    )
    # PRD-109/ARCH-040 (Phase 6) found this scenario's own real, grounding-
    # verified citations (`result.citations`, just computed above) were
    # never written back onto the question that produced them —
    # `EvalQuestion.gold_relevant_chunks` (read by both `app.eval.harness`'s
    # retrieval precision/recall and the Phase 6 sweep) was silently `None`
    # for every auto-seeded row, so those metrics had never actually been
    # computed for anything (DEVIATIONS.md #122). This question's own
    # verified citation chunk ids are exactly its gold set: they're what the
    # real pipeline retrieved AND the grounding gate verified for THIS
    # specific generated question. `_build_result` leaves `citations` empty
    # when the turn escalated instead of releasing an answer — no gold set
    # to record in that case, consistent with the field's `None` default.
    if result.citations:
        question.gold_relevant_chunks = sorted({c["chunk_id"] for c in result.citations})
    session.add(result)
    session.flush()  # materializes result.id, needed as the encryption AAD below
    crypto = get_crypto()
    if answer_text is not None:
        result.answer_enc = crypto.encrypt(
            answer_text.encode("utf-8"), aad=result_answer_aad(result.id)
        )
    if segment_dicts is not None:
        result.answer_segments_enc = crypto.encrypt(
            json.dumps(segment_dicts).encode("utf-8"), aad=result_segments_aad(result.id)
        )
    if multi_stage_answer_text is not None:
        result.multi_stage_answer_enc = crypto.encrypt(
            multi_stage_answer_text.encode("utf-8"), aad=result_multi_stage_answer_aad(result.id)
        )
    # Commit per scenario, not once at the end of the whole run (DEVIATIONS.md
    # #115): a `target_count` in the dozens means real minutes of real LLM
    # calls, and this is exactly the content a reviewer logging in is meant
    # to find already queued — an all-or-nothing transaction across the
    # entire run would make every scenario invisible to every other session
    # (a concurrent reviewer, a health check, `psql`) until generation
    # finishes completely, and would discard all already-generated scenarios
    # on a crash near the end instead of keeping what had already succeeded.
    session.commit()
    return result.id


def _invoke_pipeline(question_text: str) -> dict:
    # Lazy import: app.agents.graph_runtime pulls in every agent module at
    # import time — a real cost worth avoiding for callers (most tests) that
    # never invoke the real pipeline (same rationale as app.eval.harness's
    # own `_invoke_pipeline`).
    from app.agents.graph_runtime import invoke_graph  # noqa: PLC0415

    conversation_id = str(uuid.uuid4())
    initial_state = {
        "conversation_id": conversation_id,
        "user_id": str(uuid.uuid4()),
        "roles": ["clinician"],
        "purpose": "auto_seed_review_queue",
        # No patient_id: these narratives are deliberately framed generically
        # ("a newborn presenting with...", never "this patient" — ARCH
        # §15.1 step 4) and route as plain SCOPE-1, never touching
        # patient_record_agent — there is no live patient context to attach.
        "patient_id": None,
        "query": question_text,
        "hospital_constraint": None,
    }
    return invoke_graph(initial_state, conversation_id)


_INVOKE_PIPELINE_FN = _invoke_pipeline


def _observed_outcome_value(out: dict) -> str:
    observed = out.get("observed_outcome") or ObservedOutcome.ESCALATED
    return observed.value if hasattr(observed, "value") else str(observed)


def _extract_answer_parts(out: dict) -> tuple[str | None, list[dict], list[dict] | None]:
    """Maps one compiled-graph output onto `(answer_text, citations,
    segment_dicts)` — the shared shape both the single-stage and multi-stage
    (DEVIATIONS.md #186) extraction need, since both are the same compiled-
    graph output. `out.get("escalation")` yields `(None, [], None)`: no
    answer released, no citations, consistent with every field's `None`/
    empty default."""
    if out.get("escalation"):
        return None, [], None
    final = out.get("final_answer") or {}
    segments = [AnswerSegment(**seg) for seg in final.get("segments", [])]
    citations = [Citation(**c).model_dump(mode="json") for c in final.get("citations", [])]
    answer_text = "\n".join(s.text for s in segments)
    segment_dicts = [s.model_dump(mode="json") for s in segments]
    return answer_text, citations, segment_dicts


def _build_result(
    question: EvalQuestion,
    out: dict,
    *,
    multi_stage_query: str | None = None,
    multi_stage_fired: bool = False,
    multi_stage_out: dict | None = None,
) -> tuple[Result, str | None, list[dict] | None, str | None]:
    """Map the compiled graph's raw output onto `eval.Result` columns — the
    same shape `app.agents.query_pipeline.assemble_and_persist_response`
    reads to build the live `/query` response, reused here for this
    offline/batch path (DEVIATIONS.md #113). Returns the row (with
    `answer_enc`/`answer_segments_enc`/`multi_stage_answer_enc` still unset)
    alongside the plaintext single-stage answer text, its segment list
    (`AnswerSegment` dicts, DEVIATIONS.md #120), and the plaintext
    multi-stage answer text (DEVIATIONS.md #186) — the caller flushes first
    (materializing `Result.id`, needed as the encryption AAD per
    `app.db.models.eval.result_answer_aad`/`result_segments_aad`/
    `result_multi_stage_answer_aad`) and encrypts after, the same
    flush-then-encrypt order `app.hitl.decisions._create_hitl_decision`
    already uses for `edited_answer_enc`.

    `multi_stage_out` is `None` whenever the augmented query was never run
    (no vocabulary attested for this run, or the augmentation didn't fire
    for this record) — in that case every `multi_stage_*` column besides
    `multi_stage_query`/`multi_stage_fired` stays at its plain column
    default (empty/`{}`), not a duplicate of the single-stage answer, per
    DEVIATIONS.md #186's "no second invocation for a query that would be
    byte-identical anyway" design."""
    settings = get_settings()

    answer_text, citations, segment_dicts = _extract_answer_parts(out)

    multi_stage_answer_text: str | None = None
    multi_stage_citations: list[dict] = []
    multi_stage_retrieval_snapshot: dict = {}
    multi_stage_grounding_report: dict = {}
    if multi_stage_out is not None:
        multi_stage_answer_text, multi_stage_citations, _ = _extract_answer_parts(multi_stage_out)
        multi_stage_retrieval_snapshot = {"items": multi_stage_out.get("retrieval") or []}
        multi_stage_grounding_report = multi_stage_out.get("grounding_report") or {}

    result = Result(
        eval_question_id=question.id,
        message_id=None,
        provenance=question.provenance,
        expected_outcome=question.expected_outcome,
        observed_outcome=_observed_outcome_value(out),
        citations=citations,
        retrieval_snapshot={"items": out.get("retrieval") or []},
        grounding_report=out.get("grounding_report") or {},
        config_snapshot={
            "model_id": settings.model_id,
            "embedding_model_id": settings.embedding_model_id,
            "reranker_model_id": settings.reranker_model_id,
            "retrieval_min_score": settings.retrieval_min_score,
        },
        queue_state="open",  # visible in the review queue immediately (not "not_queued")
        multi_stage_query=multi_stage_query,
        multi_stage_fired=multi_stage_fired,
        multi_stage_citations=multi_stage_citations,
        multi_stage_retrieval_snapshot=multi_stage_retrieval_snapshot,
        multi_stage_grounding_report=multi_stage_grounding_report,
    )
    return result, answer_text, segment_dicts, multi_stage_answer_text


def run_auto_seed_review_queue(
    session: Session,
    *,
    target_count: int,
    composition: str,
    dataset_id: str | None = None,
    seed: int | None = None,
    concepts_path: str = _DEFAULT_CONCEPTS_PATH,
) -> list[uuid.UUID]:
    """Top up the review queue to `target_count` auto-generated, auto-run
    results, sourced from de-identified records — each result backed by a
    distinct patient record, never reused across this or any prior run
    (DEVIATIONS.md #114). Returns the new `Result` ids created this run
    (empty if already at/above target, if no de-identified records are
    available, or if every loaded record already has a scenario).

    `concepts_path` feeds the multi-stage audit fields (DEVIATIONS.md #186)
    — same default/attestation convention as
    `scripts/run_orchestration_ablation.py`. When it isn't attested, every
    scenario this run creates simply has no multi-stage counterpart
    (`multi_stage_query=None`, `multi_stage_fired=False`) — never a reason
    to skip or fail the primary (single-stage) generation this function
    exists for."""
    vocabulary, vocab_error = _LOAD_ATTESTED_VOCABULARY_FN(concepts_path)
    if vocabulary is None:
        logger.warning(
            "auto_seed_review_queue: multi-stage audit fields (DEVIATIONS #186) skipped for "
            "this whole run -- %s is not attested: %s",
            concepts_path,
            vocab_error,
        )

    settings = get_settings()
    already = _COUNT_EXISTING_AUTO_SEEDED_FN(session)
    remaining = target_count - already
    if remaining <= 0:
        logger.info(
            "auto_seed_review_queue: already have %d auto-generated result(s) (target %d); "
            "nothing to do",
            already,
            target_count,
        )
        return []

    records = _LOAD_RECORDS_FN(session, dataset_id=dataset_id)
    if not records:
        logger.warning(
            "auto_seed_review_queue: no de-identified records found (dataset_id=%r); skipping. "
            "Ingest one first: python -m scripts.ingest_deidentified_records "
            "--attest-deidentified --persist",
            dataset_id,
        )
        return []

    used_ids = _USED_PATIENT_IDS_FN(session)
    unused_records = [r for r in records if r[0] not in used_ids]
    if not unused_records:
        logger.warning(
            "auto_seed_review_queue: all %d loaded de-identified record(s) already have an "
            "auto-generated scenario (one scenario per record); skipping",
            len(records),
        )
        return []

    comp = Composition.parse(composition)
    slots = allocate(remaining, comp)

    state = _GenerationState(
        unused_records, seed=seed, existing_records=_EXISTING_RECORDS_FN(session)
    )
    created: list[uuid.UUID] = []
    for expected_outcome, n in slots.items():
        if n <= 0:
            continue
        made = 0
        attempts = 0
        max_attempts = max(_MIN_ATTEMPTS_PER_SLOT, n * _ATTEMPTS_PER_SLOT_MULTIPLIER)
        while made < n and attempts < max_attempts:
            attempts += 1
            result_id = _generate_one_scenario(
                session,
                state,
                expected_outcome,
                dedup_threshold=settings.qgen_dedup_threshold,
                vocabulary=vocabulary,
            )
            if result_id is not None:
                created.append(result_id)
                made += 1

        if made < n:
            logger.warning(
                "auto_seed_review_queue: only generated %d/%d %s question(s) within %d attempts "
                "(%d unused de-identified record(s) available)",
                made,
                n,
                expected_outcome,
                max_attempts,
                len(unused_records),
            )

    logger.info("auto_seed_review_queue: created %d new review-queue result(s)", len(created))
    return created
