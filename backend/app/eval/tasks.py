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
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import get_settings
from app.db.models.eval import EvalQuestion
from app.db.session import session_scope
from app.eval.harness import run_harness
from app.eval.question_gen.generate import QuestionGenerationFailed, generate_question
from app.eval.question_gen.planner import Composition, allocate
from app.worker import celery_app

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_RECORD_ID_NAMESPACE = uuid.UUID("2f9a6b6a-2d3c-4a0c-9a0b-9a9f6b9a7b21")


def _load_synthetic_records(records_dir: str) -> list[dict]:
    path = Path(records_dir) / "synthetic" / "patients.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data["records"] if isinstance(data, dict) and "records" in data else data


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
