"""Open review queue (PRD-042, PRD-047; ARCH §14.2).

GET  /review-queue                 (reviewer) -> results with < IRR_MIN_RATERS distinct raters,
                                                 visible to any clinician; shows provenance +
                                                 expected_outcome; excludes results this
                                                 clinician already rated or produced.
GET  /review-queue/{result_id}     (reviewer) -> result + citations for rating (no other raters'
                                                 scores)
Hard/adversarial cases are in the SAME queue (PRD-047).

**`eval.result` row creation is out of scope here (DEVIATIONS.md #79):** this
router only reads existing `Result` rows — it does not create them from a
live `/query` answer or an eval-harness run. `Result.answer_enc`'s AAD
(`b"eval-result-answer:" + result.id`) is defined here as the read-side
contract for whenever that writer lands.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, principal_uuid, require_role
from app.crypto.provider import get_crypto
from app.db.models.eval import RatingRound, Result

router = APIRouter()


@router.get("")
async def list_queue(
    session: Session = Depends(get_db),
    principal: Principal = Depends(require_role("reviewer")),
) -> list[dict]:
    rater_id = principal_uuid(principal)
    rounds_stmt = select(RatingRound).where(RatingRound.rater_id == rater_id)
    already_rated = {r.result_id for r in session.execute(rounds_stmt).scalars().all()}
    results_stmt = select(Result).where(Result.queue_state == "open")
    open_results = session.execute(results_stmt).scalars().all()
    return [
        {
            "result_id": str(r.id),
            "provenance": r.provenance,
            "expected_outcome": r.expected_outcome,
            "observed_outcome": r.observed_outcome,
        }
        for r in open_results
        if r.id not in already_rated
    ]


@router.get("/{result_id}")
async def get_queue_item(
    result_id: str,
    session: Session = Depends(get_db),
    _principal: Principal = Depends(require_role("reviewer")),
) -> dict:
    result = session.get(Result, uuid.UUID(result_id))
    if result is None or result.queue_state == "not_queued":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no queued result {result_id}")

    answer = None
    if result.answer_enc is not None:
        crypto = get_crypto()
        answer = crypto.decrypt(
            result.answer_enc, aad=b"eval-result-answer:" + str(result.id).encode("utf-8")
        ).decode("utf-8")

    # No other raters' scores exposed here — independence of the rank-mode
    # rating (ARCH §14.2): a reviewer's own score must not be anchored on a
    # prior rater's judgement.
    return {
        "result_id": result_id,
        "provenance": result.provenance,
        "expected_outcome": result.expected_outcome,
        "answer": answer,
        "citations": result.citations,
        "grounding_report": result.grounding_report,
    }
