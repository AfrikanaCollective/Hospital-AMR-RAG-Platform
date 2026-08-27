"""Rubric (rank mode) endpoints (PRD-040, PRD-041, PRD-042, PRD-044; ARCH §14).

GET  /rubric/domains                          -> the 11 domains + Likert anchors (reference)
POST /rubric/results/{result_id}/ratings      (reviewer) -> one rating_round: 11 domain scores
      (1-5) + optional comment + optional linked accept-axis action. Enforces
      distinct-rater (rating_round UNIQUE (result_id, rater_id)).
GET  /rubric/results/{result_id}              -> rating history + IRR (once archived)
IRR per domain computed at >= IRR_MIN_RATERS distinct raters, then archived.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role
from app.rubric.domains import RUBRIC_DOMAINS

router = APIRouter()


@router.get("/domains")
async def list_domains() -> list[dict[str, object]]:
    return [d.as_reference() for d in RUBRIC_DOMAINS]


@router.post("/results/{result_id}/ratings", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("reviewer"))])
async def submit_rating(result_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: rubric workflow (ARCH §14.2).")


@router.get("/results/{result_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED,
            dependencies=[Depends(require_role("reviewer", "admin"))])
async def get_result_ratings(result_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: rubric workflow (ARCH §14.5).")
