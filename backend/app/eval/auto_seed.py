"""Auto-seed the rubric review queue from de-identified records
(ARCH §14.2, §15; DEVIATIONS.md #113).

Wires together, end to end:
1. `app.eval.deidentified_source.load_deidentified_records` — already-ingested
   de-identified patient records (never synthetic ones — this pipeline is
   specifically "from the existing de-identified anonymised patient-level
   records").
2. `app.eval.question_gen` (planner + generator, unchanged) — a 60/20/20
   `expected_outcome`-stratified plan of unique, scope-1-framed narrative
   questions, now with the diversity filter (ARCH §15.1 step 7,
   `app.eval.question_gen.diversity`) actually enforced.
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
near-duplicate filter's `accepted_embeddings` seed is the embedding of every
already-accepted auto-generated question (persisted at creation time in
`EvalQuestion.generator_meta["embedding"]`, `_existing_accepted_embeddings`)
— not an empty list — so a later top-up run (e.g. raising
`QGEN_AUTO_SEED_COUNT`) cannot re-accept a narrative near-duplicate of one
already queued in an earlier run.

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
from app.db.models.eval import EvalQuestion, Result, result_answer_aad, result_segments_aad
from app.eval.deidentified_source import load_deidentified_records
from app.eval.question_gen.diversity import is_near_duplicate
from app.eval.question_gen.generate import QuestionGenerationFailed, generate_question
from app.eval.question_gen.planner import Composition, allocate
from app.ingestion.embed import embed_texts
from app.llm.gateway import LLMGatewayError
from app.logging import get_logger
from app.schemas.citation import Citation
from app.schemas.enums import ExpectedOutcome, ObservedOutcome, Provenance
from app.schemas.query import AnswerSegment

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

_LOAD_RECORDS_FN = load_deidentified_records
_EMBED_FN = embed_texts

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


def _existing_accepted_embeddings(session: Session) -> list[list[float]]:
    """Embeddings of every already-accepted auto-generated question's
    narrative, read back from `EvalQuestion.generator_meta["embedding"]`
    (DEVIATIONS.md #114) — seeds the diversity filter so a later top-up run
    cannot re-accept a near-duplicate of one already queued. A row from
    before this change has no `"embedding"` key and is skipped, not treated
    as an error — it simply isn't checked against (no narrative text is
    re-embedded retroactively; the practical exposure is limited to
    installations that ran the auto-seed pipeline before this fix, which per
    DEVIATIONS.md #113 was `QGEN_AUTO_SEED_COUNT=30`, a small, one-time,
    disclosed gap, not one this change silently re-introduces going
    forward).

    Also skips a row whose `"embedding_model_id"` doesn't match the
    currently configured `EMBEDDING_MODEL_ID` (DEVIATIONS.md #119) — a stale
    embedding from a since-replaced model is not directly comparable by
    cosine similarity to one from the current model, and including it
    produced unreliable near-duplicate results (found live when this
    deployment switched `EMBEDDING_BACKEND` gateway -> local mid-generation).
    A row from before #119 has no `"embedding_model_id"` key either and is
    skipped the same way — same disclosed, non-silent gap as the paragraph
    above, not a new one."""
    stmt = select(EvalQuestion.generator_meta).where(
        EvalQuestion.provenance == Provenance.AUTO_GENERATED.value
    )
    current_model_id = get_settings().embedding_model_id
    out: list[list[float]] = []
    for raw_meta in session.execute(stmt).scalars().all():
        meta = raw_meta or {}
        embedding = meta.get("embedding")
        if embedding and meta.get("embedding_model_id") == current_model_id:
            out.append(embedding)
    return out


_EXISTING_EMBEDDINGS_FN = _existing_accepted_embeddings


class _GenerationState:
    """Mutable state threaded through one `run_auto_seed_review_queue` call
    (DEVIATIONS.md #114): the shuffled candidate pool + cursor, the
    within-run record-reuse guard, and the diversity filter's accepted
    embeddings — seeded from every prior run's output, not just this one."""

    def __init__(
        self,
        records: list[tuple[uuid.UUID, dict]],
        *,
        seed: int | None,
        existing_embeddings: list[list[float]],
    ) -> None:
        self.shuffled = records[:]
        random.Random(seed).shuffle(self.shuffled)
        self.cursor = 0
        self.used_this_run: set[uuid.UUID] = set()
        self.accepted_embeddings: list[list[float]] = list(existing_embeddings)

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
    gateway: object | None,
) -> uuid.UUID | None:
    """One attempt: pick a candidate record, generate + validate a
    narrative, reject a near-duplicate, run the real pipeline, persist
    `EvalQuestion` + `Result`, and commit (DEVIATIONS.md #115) — returns the
    new `Result.id`, or `None` for any rejection (already used this run,
    generation failed, near-duplicate, or a transient gateway error —
    DEVIATIONS.md #116) — the caller retries with the next candidate, not
    this function.

    Every network call (narrative generation, embedding, the real graph
    invocation) happens *before* anything is added to `session` — found
    live (DEVIATIONS.md #116): a transient gateway failure (a timeout, a
    503) during the graph invocation, uncaught, crashed the whole Celery
    task outright, and since nothing auto-retries or reschedules it, a
    single blip silently stalled generation until the next container
    restart — observed stalled for ~12 hours in exactly this way. Ordering
    the real pipeline call before any DB write also means a transient
    failure never leaves a half-written `EvalQuestion` with no matching
    `Result` sitting pending in the session for a later commit to pick up
    by accident."""
    candidate = state.next_candidate()
    if candidate is None:
        return None
    patient_id, record = candidate
    try:
        generated = generate_question(
            record,
            expected_outcome,
            gateway=gateway,  # type: ignore[arg-type]
        )
    except QuestionGenerationFailed:
        return None
    except (httpx.HTTPError, LLMGatewayError) as exc:
        logger.warning(
            "auto_seed_review_queue: transient gateway error generating a narrative for "
            "record %r, skipping this attempt: %s",
            patient_id,
            exc,
        )
        return None

    try:
        [embedding] = _EMBED_FN([generated["text"]], is_query=False)
        if is_near_duplicate(embedding, state.accepted_embeddings, threshold=dedup_threshold):
            return None
        out = _INVOKE_PIPELINE_FN(generated["text"])
    except (httpx.HTTPError, LLMGatewayError) as exc:
        logger.warning(
            "auto_seed_review_queue: transient gateway error embedding/running the pipeline "
            "for record %r, skipping this attempt: %s",
            patient_id,
            exc,
        )
        return None

    state.accepted_embeddings.append(embedding)
    state.used_this_run.add(patient_id)

    generator_meta = dict(generated.get("generator_meta") or {})
    generator_meta["embedding"] = embedding
    # Which model produced `embedding` above — read back by
    # `_existing_accepted_embeddings` so a later switch of `EMBEDDING_MODEL_ID`
    # can't silently compare across two different embedding spaces
    # (DEVIATIONS.md #119: found live — mixing a `qllama/bge-large-en-v1.5`-gateway
    # embedding with a `BAAI/bge-large-en-v1.5`-local one in the same
    # cosine-similarity comparison produced unreliable near-duplicate results).
    generator_meta["embedding_model_id"] = get_settings().embedding_model_id
    question = EvalQuestion(
        text=generated["text"],
        provenance=generated["provenance"],
        expected_outcome=generated["expected_outcome"],
        source_record_id=patient_id,
        target_guideline_ref=generated.get("target_guideline_ref"),
        generator_meta=generator_meta,
        in_fixed_testset=False,
    )
    session.add(question)
    session.flush()

    result, answer_text, segment_dicts = _build_result(question, out)
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


def _build_result(
    question: EvalQuestion, out: dict
) -> tuple[Result, str | None, list[dict] | None]:
    """Map the compiled graph's raw output onto `eval.Result` columns — the
    same shape `app.agents.query_pipeline.assemble_and_persist_response`
    reads to build the live `/query` response, reused here for this
    offline/batch path (DEVIATIONS.md #113). Returns the row (with
    `answer_enc`/`answer_segments_enc` still unset) alongside the plaintext
    answer text and the segment list (`AnswerSegment` dicts, DEVIATIONS.md
    #120) — the caller flushes first (materializing `Result.id`, needed as
    the encryption AAD per `app.db.models.eval.result_answer_aad`/
    `result_segments_aad`) and encrypts after, the same flush-then-encrypt
    order `app.hitl.decisions._create_hitl_decision` already uses for
    `edited_answer_enc`."""
    settings = get_settings()

    citations: list[dict] = []
    answer_text: str | None = None
    segment_dicts: list[dict] | None = None
    if not out.get("escalation"):
        final = out.get("final_answer") or {}
        segments = [AnswerSegment(**seg) for seg in final.get("segments", [])]
        citations = [Citation(**c).model_dump(mode="json") for c in final.get("citations", [])]
        answer_text = "\n".join(s.text for s in segments)
        segment_dicts = [s.model_dump(mode="json") for s in segments]

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
    )
    return result, answer_text, segment_dicts


def run_auto_seed_review_queue(
    session: Session,
    *,
    target_count: int,
    composition: str,
    dataset_id: str | None = None,
    seed: int | None = None,
    gateway: object | None = None,
) -> list[uuid.UUID]:
    """Top up the review queue to `target_count` auto-generated, auto-run
    results, sourced from de-identified records — each result backed by a
    distinct patient record, never reused across this or any prior run
    (DEVIATIONS.md #114). Returns the new `Result` ids created this run
    (empty if already at/above target, if no de-identified records are
    available, or if every loaded record already has a scenario)."""
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
        unused_records, seed=seed, existing_embeddings=_EXISTING_EMBEDDINGS_FN(session)
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
                gateway=gateway,
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
