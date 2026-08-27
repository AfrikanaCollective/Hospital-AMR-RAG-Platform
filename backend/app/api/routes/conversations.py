"""Conversation / session memory endpoints (ARCH-017; PRD-022, PRD-NG-011).

GET  /conversations/{id}            -> conversation with messages + citations
POST /conversations                 -> start a session (<= 1 patient_id)
POST /conversations/{id}/handoff    -> transfer ownership (interface only, MVP)
A conversation is bound to at most one patient_id (PRD-NG-011).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_conversation() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: conversation memory (ARCH-017).")


@router.get("/{conversation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_conversation(conversation_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 3: conversation memory (ARCH-017).")
