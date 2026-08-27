"""Eval harness + auto-question endpoints (PRD-060..PRD-073; ARCH §15, §16).

POST /eval/questions/generate   (admin) -> enqueue auto-question generation (60/20/20)
GET  /eval/questions                     -> list, filterable by provenance + expected_outcome
POST /eval/runs                 (admin) -> run the harness against the fixed test set (pinned config)
GET  /eval/runs/{id}                     -> report (by expected_outcome; auto vs clinician separate)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role

router = APIRouter()


@router.post("/questions/generate", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("admin"))])
async def generate_questions() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: question generator (ARCH §15).")


@router.post("/runs", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("admin"))])
async def start_eval_run() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: eval harness (ARCH §16).")
