"""HITL escalation + accept-axis endpoints (PRD-030, PRD-032, PRD-033; ARCH §12, §13).

GET  /hitl/escalations/{id}
POST /hitl/escalations/{id}/decision   (reviewer)  -> full_accept | partial_accept | reject
      Effects on shown answer / conversation memory / patient_context per ARCH §13.2.
Every decision writes an immutable audit_event and updates escalation + queue state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role

router = APIRouter()


@router.get("/escalations/{escalation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_escalation(escalation_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: HITL (ARCH §12).")


@router.post("/escalations/{escalation_id}/decision", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("reviewer"))])
async def submit_decision(escalation_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: accept axis (ARCH §13.2).")
