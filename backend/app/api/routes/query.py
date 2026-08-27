"""Query endpoint (SCOPE-1.1, SCOPE-2.1, SCOPE-2.2; PRD-011..PRD-016, PRD-107).

POST /query
  Body: QueryRequest (question, optional conversation_id, optional patient_id,
        purpose-of-use via header).
  Flow (Phase 3): orchestrator scope-classifies -> retrieval -> [patient-record
        -> stage-classifier / missing-info] -> synthesis -> citation-verifier
        grounding gate -> assemble + disclaimer OR escalate.
  Never returns an ungrounded answer (PRD-NFR-2). SCOPE-2.3/2.4 intent ->
  escalation with trigger_code=scope_boundary (never answered).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, current_principal, purpose_of_use
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter()


@router.post("", response_model=QueryResponse, status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def submit_query(
    _body: QueryRequest,
    _principal: Principal = Depends(current_principal),
    _purpose: str = Depends(purpose_of_use),
) -> QueryResponse:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Phase 3: multi-agent orchestration + grounding gate (ARCH-016, ARCH-015).",
    )
