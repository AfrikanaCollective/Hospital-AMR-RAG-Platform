"""`memory` schema — conversation + per-patient context + checkpoints (ARCH §4.3, ARCH-017).

`patient_context.kind` is a closed set of NON-diagnostic kinds. The repository
layer (`app.memory.patient_context`) rejects recommendation-shaped writes
(ARCH-024). No cross-patient reads.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPk

SCHEMA = "memory"

PATIENT_CONTEXT_KINDS = ("guideline_match", "stage_classification", "missing_info", "note")


class Conversation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = {"schema": SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID | None] = mapped_column()  # <= 1 patient per conversation
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|closed|handoff
    closed_at: Mapped[datetime | None] = mapped_column()


class Message(UUIDPk, TimestampMixin, Base):
    __tablename__ = "message"
    __table_args__ = {"schema": SCHEMA}

    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.conversation.id"))
    turn: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system|tool|reviewer
    content_enc: Mapped[bytes] = mapped_column(LargeBinary)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)  # ids + scores
    model_id: Mapped[str | None] = mapped_column(String(128))
    grounding: Mapped[dict] = mapped_column(JSONB, default=dict)
    hitl_ref: Mapped[uuid.UUID | None] = mapped_column()


class PatientContext(UUIDPk, TimestampMixin, Base):
    __tablename__ = "patient_context"
    __table_args__ = {"schema": SCHEMA}

    patient_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(32))  # one of PATIENT_CONTEXT_KINDS
    payload: Mapped[dict] = mapped_column(JSONB)  # structured; NO free-form "next step" fields
    provenance: Mapped[str] = mapped_column(
        String(24), default="model_provisional"
    )  # model_provisional | reviewer_accepted | reviewer_edited | rejected
    source_message_id: Mapped[uuid.UUID | None] = mapped_column()
    result_id: Mapped[uuid.UUID | None] = mapped_column()  # for rollback on reject
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID | None] = mapped_column()


class LangGraphCheckpoint(Base):
    """Placeholder — the langgraph-checkpoint-postgres library manages the real
    table(s). Declared here only so migrations are aware of the schema."""

    __tablename__ = "langgraph_checkpoint"
    __table_args__ = {"schema": SCHEMA}

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    tied_escalation_id: Mapped[uuid.UUID | None] = mapped_column()  # retain until resolved
    created_at: Mapped[datetime] = mapped_column()


# NOTE: operational hot state (active window, streaming partials, rate
# counters) lives in Redis keyed by conversation_id with a TTL (ARCH §4.3),
# not in Postgres. It is authoritative only until persisted here.
