"""Conversation / session memory endpoints (ARCH-017; PRD-022, PRD-NG-011).

GET  /conversations/{id}            -> conversation with messages + citations
POST /conversations                 -> start a session (<= 1 patient_id)
POST /conversations/{id}/handoff    -> transfer ownership (interface only, MVP)
A conversation is bound to at most one patient_id (PRD-NG-011).

`POST /query` (app.api.routes.query) also creates a conversation implicitly
when no `conversation_id` is given — this endpoint exists for a client that
wants to create one explicitly up front (e.g. to attach a patient before the
first question) and for retrieving history.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, get_db, principal_uuid
from app.memory.conversation import ConversationNotFoundError, create_conversation, get_conversation

router = APIRouter()


class CreateConversationRequest(BaseModel):
    patient_id: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation_route(
    body: CreateConversationRequest,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    conversation = create_conversation(
        session,
        user_id=principal_uuid(principal),
        patient_id=uuid.UUID(body.patient_id) if body.patient_id else None,
    )
    return {"id": str(conversation.id), "status": conversation.status}


@router.get("/{conversation_id}")
async def get_conversation_route(
    conversation_id: str,
    session: Session = Depends(get_db),
    _principal: Principal = Depends(current_principal),
) -> dict:
    try:
        return get_conversation(session, uuid.UUID(conversation_id))
    except ConversationNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{conversation_id}/handoff", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def handoff_conversation(conversation_id: str) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Conversation handoff is an interface-only stub for MVP (ARCH-017).",
    )
