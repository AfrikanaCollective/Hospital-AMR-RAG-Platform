"""Open review queue (PRD-042, PRD-047; ARCH §14.2).

GET  /review-queue                 (reviewer) -> results with < IRR_MIN_RATERS distinct raters,
                                                 visible to any clinician; shows provenance +
                                                 expected_outcome; excludes results this
                                                 clinician already rated or produced.
GET  /review-queue/{result_id}     (reviewer) -> result + citations for rating (no other raters' scores)
Hard/adversarial cases are in the SAME queue (PRD-047).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role

router = APIRouter()


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED,
            dependencies=[Depends(require_role("reviewer"))])
async def list_queue() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: review queue (ARCH §14.2).")


@router.get("/{result_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED,
            dependencies=[Depends(require_role("reviewer"))])
async def get_queue_item(result_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: review queue (ARCH §14.2).")
