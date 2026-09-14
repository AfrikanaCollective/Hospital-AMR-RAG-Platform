"""Session conversation memory (ARCH §11; PRD-022).

Durable messages (with retrieved_chunk_ids + scores, citations, grounding
reports, HITL actions) in Postgres; active window / streaming partials in
Redis (TTL, not implemented in MVP — see module docstring precedent in
`app.memory.checkpointer`). A conversation is bound to <= 1 patient_id
(PRD-NG-011), enforced by the caller (the orchestrator only ever sets
`patient_id` once, at conversation creation).

`Message.content_enc` is envelope-encrypted (ARCH-032), AAD-bound to its
conversation id so a blob cannot be replayed into a different conversation.

`_get_conversation_row` / `_list_messages` are the only two points that touch
the database — indirection so tests exercise the real encrypt/decrypt +
shaping logic with a trivial fake session (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.crypto.provider import get_crypto
from app.db.models.memory import Conversation, Message

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_AAD_NAMESPACE = b"conversation-message:"


class ConversationNotFoundError(LookupError):
    pass


def _get_conversation_row(session: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def _list_messages(session: Session, conversation_id: uuid.UUID) -> list[Message]:
    return list(
        session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.turn)
        )
        .scalars()
        .all()
    )


def create_conversation(
    session: Session, *, user_id: uuid.UUID, patient_id: uuid.UUID | None = None
) -> Conversation:
    conversation = Conversation(user_id=user_id, patient_id=patient_id, status="active")
    session.add(conversation)
    session.flush()
    return conversation


def append_message(
    session: Session,
    conversation_id: uuid.UUID,
    *,
    turn: int,
    role: str,
    content: str,
    citations: list | None = None,
    retrieved_chunk_ids: list | None = None,
    model_id: str | None = None,
    grounding: dict | None = None,
    hitl_ref: uuid.UUID | None = None,
) -> Message:
    crypto = get_crypto()
    content_enc = crypto.encrypt(
        content.encode("utf-8"), aad=_AAD_NAMESPACE + str(conversation_id).encode("utf-8")
    )
    message = Message(
        conversation_id=conversation_id,
        turn=turn,
        role=role,
        content_enc=content_enc,
        citations=citations or [],
        retrieved_chunk_ids=retrieved_chunk_ids or [],
        model_id=model_id,
        grounding=grounding or {},
        hitl_ref=hitl_ref,
    )
    session.add(message)
    session.flush()
    return message


def get_conversation(session: Session, conversation_id: uuid.UUID) -> dict[str, Any]:
    conversation = _get_conversation_row(session, conversation_id)
    if conversation is None:
        raise ConversationNotFoundError(f"no conversation {conversation_id}")
    crypto = get_crypto()
    messages = _list_messages(session, conversation_id)
    return {
        "id": str(conversation.id),
        "user_id": str(conversation.user_id),
        "patient_id": str(conversation.patient_id) if conversation.patient_id else None,
        "status": conversation.status,
        "messages": [
            {
                "id": str(m.id),
                "turn": m.turn,
                "role": m.role,
                "content": crypto.decrypt(
                    m.content_enc, aad=_AAD_NAMESPACE + str(conversation_id).encode("utf-8")
                ).decode("utf-8"),
                "citations": m.citations,
                "retrieved_chunk_ids": m.retrieved_chunk_ids,
                "model_id": m.model_id,
                "grounding": m.grounding,
                "hitl_ref": str(m.hitl_ref) if m.hitl_ref else None,
            }
            for m in messages
        ],
    }
