"""Open review queue (PRD-042, PRD-047; ARCH §14.2).

GET  /review-queue                 (reviewer) -> results this reviewer may currently pick to
                                                 rate. Visibility + priority rule
                                                 (DEVIATIONS.md #113): only 0-2-round `open`
                                                 results, excluding anything this reviewer
                                                 already rated; if ANY of those has 1-2 rounds
                                                 ("in progress"), ONLY those are returned —
                                                 finishing an in-progress result takes priority
                                                 over starting a fresh (0-round) one, which only
                                                 becomes selectable once no in-progress result
                                                 remains (`app.rubric.workflow.select_queue_items`,
                                                 the actual rule; `list_queue_candidates`, the
                                                 DB read).
GET  /review-queue/{result_id}     (reviewer) -> result + citations for rating (no other raters'
                                                 scores)
Hard/adversarial cases are in the SAME queue (PRD-047).

**`eval.result` row creation** (DEVIATIONS.md #79, #113): this router only
reads existing `Result` rows. `app.eval.auto_seed` is the first writer
(auto-generated, de-identified-record-sourced hypotheticals, run through the
real query pipeline and queued `open` immediately); a live `/query` result
or a clinician-submitted one may write here too in the future, under the
same `Result.answer_enc` AAD contract (`app.db.models.eval.result_answer_aad`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, principal_uuid, require_role
from app.crypto.provider import get_crypto
from app.db.models.eval import Result, result_answer_aad
from app.rubric.workflow import list_queue_candidates, select_queue_items

router = APIRouter()

_LIST_QUEUE_CANDIDATES_FN = list_queue_candidates


@router.get("")
async def list_queue(
    session: Session = Depends(get_db),
    principal: Principal = Depends(require_role("reviewer")),
) -> list[dict]:
    rater_id = principal_uuid(principal)
    selected = select_queue_items(_LIST_QUEUE_CANDIDATES_FN(session, rater_id))
    if not selected:
        return []
    result_ids = [c.result_id for c in selected]
    results = {
        r.id: r
        for r in session.execute(select(Result).where(Result.id.in_(result_ids))).scalars().all()
    }
    return [
        {
            "result_id": str(candidate.result_id),
            "provenance": results[candidate.result_id].provenance,
            "expected_outcome": results[candidate.result_id].expected_outcome,
            "observed_outcome": results[candidate.result_id].observed_outcome,
            "distinct_rater_count": candidate.distinct_rater_count,
        }
        for candidate in selected
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
        answer = crypto.decrypt(result.answer_enc, aad=result_answer_aad(result.id)).decode("utf-8")

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
