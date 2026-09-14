"""Eval harness + auto-question endpoints (PRD-060..PRD-073; ARCH §15, §16).

POST /eval/questions/generate   (admin) -> enqueue auto-question generation (60/20/20)
GET  /eval/questions                     -> list, filterable by provenance + expected_outcome
POST /eval/runs                 (admin) -> enqueue the harness against the fixed test set (pinned
                                           config)
GET  /eval/runs/{id}                     -> report (by expected_outcome; auto vs clinician separate)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require_role
from app.db.models.eval import EvalQuestion, EvalRun
from app.eval.tasks import generate_questions, run_harness_task
from app.schemas.eval import GenerateQuestionsRequest

router = APIRouter()


@router.post("/questions/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_questions_route(
    body: GenerateQuestionsRequest, _principal: Principal = Depends(require_role("admin"))
) -> dict:
    generate_questions.delay(
        count=body.count,
        composition=body.composition,
        seed=body.seed,
        add_to_fixed_testset=body.add_to_fixed_testset,
    )
    return {"enqueued": True, "count": body.count, "composition": body.composition}


@router.get("/questions")
async def list_questions(
    provenance: str | None = Query(default=None),
    expected_outcome: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(EvalQuestion)
    if provenance:
        stmt = stmt.where(EvalQuestion.provenance == provenance)
    if expected_outcome:
        stmt = stmt.where(EvalQuestion.expected_outcome == expected_outcome)
    rows = session.execute(stmt).scalars().all()
    return [
        {
            "id": str(q.id),
            "text": q.text,
            "provenance": q.provenance,
            "expected_outcome": q.expected_outcome,
            "in_fixed_testset": q.in_fixed_testset,
        }
        for q in rows
    ]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_eval_run(
    snapshot: str = "latest", _principal: Principal = Depends(require_role("admin"))
) -> dict:
    run_harness_task.delay(snapshot=snapshot)
    return {"enqueued": True, "snapshot": snapshot}


@router.get("/runs/{run_id}")
async def get_eval_run(
    run_id: str,
    session: Session = Depends(get_db),
    _principal: Principal = Depends(require_role("admin", "reviewer")),
) -> dict:
    run = session.get(EvalRun, uuid.UUID(run_id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no eval run {run_id}")
    return {
        "id": str(run.id),
        "snapshot_label": run.snapshot_label,
        "passed": run.passed,
        "report": run.report,
    }
