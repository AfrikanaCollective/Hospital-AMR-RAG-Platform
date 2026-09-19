"""Celery tasks for eval + question generation (ARCH §15, §16).

`generate_questions` wires the composition planner (`app.eval.question_gen.planner`,
Phase 1) and the per-record narrative generator (`app.eval.question_gen.generate`,
Phase 2) together and persists the results as `eval.eval_question` rows — the
part DEVIATIONS.md #67 flagged as not yet done ("generate_question returns
the shaped dict; a caller writes it to the DB").

**Source-record selection (DEVIATIONS.md #78):** step 2 of ARCH §15.1
("pick a source record matched to a guideline's applicability") is still
deferred (DEVIATIONS.md #67 — needs a live, ingested corpus to match
against). This task instead draws from the bundled synthetic dataset
(`PATIENT_RECORDS_DIR/synthetic/patients.json`) in a seeded-shuffle,
round-robin order — real synthetic records, no invented data, just no
guideline-fit judgement behind which record fills which composition slot yet.
`target_guideline_topic` is left `None` for every generated question as a
result; a future step-2 implementation would pass a real topic here, which
`generate_question` already accepts.

**`gold_relevant_chunks` is now populated at generation time (DEVIATIONS.md
#151, fixing the gap DEVIATIONS.md #122 identified and deliberately left
open here).** Same pattern `app.eval.auto_seed._generate_one_scenario`
already uses: invoke the real pipeline once with the generated narrative and
take its own grounding-verified citations as the gold set — the chunks the
real retrieval+rerank+grounding-gate pipeline actually retrieved and
verified for *this specific* question, not a separately-computed
approximation. Unlike `auto_seed`, no `eval.Result` row is persisted here —
`app.eval.harness` invokes the pipeline again, separately, each time it
actually scores a fixed-testset question, so this invocation exists only to
capture the gold set, and a transient gateway error during it is swallowed
(logged), not raised: the narrative itself already generated successfully
and is still a valid question without a gold set.
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.config import get_settings
from app.db.models.eval import EvalQuestion
from app.db.session import session_scope
from app.eval.auto_seed import run_auto_seed_review_queue
from app.eval.harness import run_harness
from app.eval.question_gen.deterministic import build_deterministic_narrative
from app.eval.question_gen.generate import QuestionGenerationFailed, generate_question
from app.eval.question_gen.planner import Composition, allocate
from app.llm.gateway import LLMGatewayError
from app.logging import get_logger
from app.schemas.enums import ExpectedOutcome, Provenance
from app.worker import celery_app

logger = get_logger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_RECORD_ID_NAMESPACE = uuid.UUID("2f9a6b6a-2d3c-4a0c-9a0b-9a9f6b9a7b21")


def _load_synthetic_records(records_dir: str) -> list[dict]:
    path = Path(records_dir) / "synthetic" / "patients.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data["records"] if isinstance(data, dict) and "records" in data else data


def _invoke_pipeline(question_text: str) -> dict:
    # Lazy import: app.agents.graph_runtime pulls in every agent module at
    # import time — a real cost worth avoiding for callers (most tests) that
    # never invoke the real pipeline (same rationale as app.eval.harness's
    # and app.eval.auto_seed's own `_invoke_pipeline`).
    from app.agents.graph_runtime import invoke_graph  # noqa: PLC0415

    conversation_id = str(uuid.uuid4())
    initial_state = {
        "conversation_id": conversation_id,
        "user_id": str(uuid.uuid4()),
        "roles": ["clinician"],
        "purpose": "eval_fixed_testset_generation",
        # No patient_id: these narratives are scope-1 framed ("a newborn
        # presenting with...", never "this patient" — ARCH §15.1 step 4) and
        # route as plain SCOPE-1, never touching patient_record_agent — same
        # reasoning as app.eval.auto_seed._invoke_pipeline.
        "patient_id": None,
        "query": question_text,
        "hospital_constraint": None,
    }
    return invoke_graph(initial_state, conversation_id)


_INVOKE_PIPELINE_FN = _invoke_pipeline


def _capture_gold_relevant_chunks(question_text: str) -> list[str] | None:
    """Run the real pipeline once to capture this question's own
    grounding-verified citations as its gold chunk set (DEVIATIONS.md #151).
    `None` if the pipeline escalated / found no guideline (no citations to
    record, matching the field's `None` default — the same as a genuinely
    empty `Result.citations` in `app.eval.auto_seed`) or a transient gateway
    error prevented the call entirely."""
    try:
        out = _INVOKE_PIPELINE_FN(question_text)
    except (httpx.HTTPError, LLMGatewayError) as exc:
        logger.warning(
            "generate_questions: transient gateway error capturing gold_relevant_chunks "
            "for a generated question, leaving it unset: %s",
            exc,
        )
        return None
    if out.get("escalation"):
        return None
    citations = (out.get("final_answer") or {}).get("citations", [])
    if not citations:
        return None
    return sorted({c["chunk_id"] for c in citations})


def _run_generate_questions(
    session: Session,
    *,
    count: int,
    composition: str,
    seed: int | None = None,
    add_to_fixed_testset: bool = True,
    gateway: object | None = None,
) -> list[uuid.UUID]:
    settings = get_settings()
    comp = Composition.parse(composition)
    slots = allocate(count, comp)

    records = _load_synthetic_records(settings.patient_records_dir)
    if not records:
        raise RuntimeError(
            f"no synthetic records found under {settings.patient_records_dir}/synthetic/ "
            "to generate questions from"
        )
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)

    created: list[uuid.UUID] = []
    cursor = 0
    for expected_outcome, n in slots.items():
        for _ in range(n):
            record = shuffled[cursor % len(shuffled)]
            cursor += 1
            try:
                generated = generate_question(record, expected_outcome, gateway=gateway)  # type: ignore[arg-type]
            except QuestionGenerationFailed:
                continue  # one bad generation doesn't fail the whole batch
            row = EvalQuestion(
                text=generated["text"],
                provenance=generated["provenance"],
                expected_outcome=generated["expected_outcome"],
                source_record_id=uuid.uuid5(
                    _RECORD_ID_NAMESPACE, str(generated["source_record_id"])
                ),
                target_guideline_ref=generated.get("target_guideline_ref"),
                generator_meta=generated.get("generator_meta"),
                in_fixed_testset=add_to_fixed_testset,
            )
            row.gold_relevant_chunks = _capture_gold_relevant_chunks(generated["text"])
            session.add(row)
            session.flush()
            created.append(row.id)
    return created


def _run_generate_deterministic_questions(
    session: Session,
    *,
    topic: str,
    expected_outcome: str = ExpectedOutcome.WELL_SUPPORTED,
    add_to_fixed_testset: bool = False,
    records_dir: str | None = None,
) -> list[uuid.UUID]:
    """Deterministic, LLM-free alternative to `_run_generate_questions`
    (DEVIATIONS.md #156) — for ablation-study question sets where exact,
    reproducible content (including an explicit list of assessed-and-absent
    findings, not just present ones) matters more than narrative
    naturalness. `app.eval.question_gen.deterministic.build_deterministic_narrative`
    builds only from the record's own field values, so there is no
    fabrication risk and no validator/retry step is needed. `topic` is the
    caller's responsibility (ARCH §15.1 step 2's automatic topic-matching is
    not implemented — DEVIATIONS.md #67/#156); one call produces one
    question per bundled synthetic record, all sharing the same `topic`."""
    settings = get_settings()
    records = _load_synthetic_records(records_dir or settings.patient_records_dir)
    if not records:
        raise RuntimeError(
            f"no synthetic records found under "
            f"{records_dir or settings.patient_records_dir}/synthetic/ "
            "to generate questions from"
        )

    created: list[uuid.UUID] = []
    for record in records:
        text = build_deterministic_narrative(record, topic=topic)
        row = EvalQuestion(
            text=text,
            provenance=Provenance.AUTO_GENERATED,
            expected_outcome=expected_outcome,
            source_record_id=uuid.uuid5(_RECORD_ID_NAMESPACE, str(record.get("record_id"))),
            target_guideline_ref={"topic": topic},
            generator_meta={"template_version": "deterministic-v1"},
            in_fixed_testset=add_to_fixed_testset,
        )
        row.gold_relevant_chunks = _capture_gold_relevant_chunks(text)
        session.add(row)
        session.flush()
        created.append(row.id)
    return created


@celery_app.task(name="eval.generate_questions")
def generate_questions(
    count: int,
    composition: str = "60,20,20",
    seed: int | None = None,
    add_to_fixed_testset: bool = True,
) -> None:
    with session_scope() as session:
        _run_generate_questions(
            session,
            count=count,
            composition=composition,
            seed=seed,
            add_to_fixed_testset=add_to_fixed_testset,
        )


@celery_app.task(name="eval.run_harness")
def run_harness_task(snapshot: str = "latest") -> None:
    run_harness(snapshot=snapshot)


@celery_app.task(name="eval.auto_seed_review_queue")
def auto_seed_review_queue_task() -> None:
    """Enqueued from `app.main`'s FastAPI lifespan hook on every startup
    when `QGEN_AUTO_SEED_ENABLED` (default true) — ARCH §14.2/§15;
    DEVIATIONS.md #113. Runs in the worker, not inline in the API process,
    so container startup is never blocked by N LLM calls + N full pipeline
    runs. Idempotent (`run_auto_seed_review_queue` tops up to
    `QGEN_AUTO_SEED_COUNT`, doesn't duplicate) and fails soft: a placeholder
    `MODEL_ID` or a missing de-identified dataset logs a clear message and
    returns rather than raising and being retried forever."""
    settings = get_settings()
    if not settings.qgen_auto_seed_enabled:
        return
    if settings.is_model_placeholder():
        logger.warning(
            "auto_seed_review_queue_task: MODEL_ID is the placeholder; skipping "
            "review-queue auto-seeding until a real model id is configured."
        )
        return
    with session_scope() as session:
        run_auto_seed_review_queue(
            session,
            target_count=settings.qgen_auto_seed_count,
            composition=settings.qgen_composition,
            dataset_id=settings.qgen_auto_seed_dataset_id or None,
        )
