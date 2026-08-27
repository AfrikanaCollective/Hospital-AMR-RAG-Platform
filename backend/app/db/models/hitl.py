"""`hitl` schema — escalations + accept-axis decisions (ARCH §4.4, §12, §13)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPk

SCHEMA = "hitl"


class Escalation(UUIDPk, TimestampMixin, Base):
    __tablename__ = "escalation"
    __table_args__ = {"schema": SCHEMA}

    conversation_id: Mapped[uuid.UUID | None] = mapped_column()
    message_id: Mapped[uuid.UUID | None] = mapped_column()
    trigger_code: Mapped[str] = mapped_column(String(48))  # app.schemas.enums.EscalationTrigger
    trigger_detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    candidate_answer_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(16), default="open")  # open|in_review|resolved
    resolution: Mapped[str | None] = mapped_column(String(16))  # accepted|partial|rejected
    resolved_by: Mapped[uuid.UUID | None] = mapped_column()
    resolved_at: Mapped[datetime | None] = mapped_column()


class HitlDecision(UUIDPk, TimestampMixin, Base):
    """Accept axis; append-only (ARCH §13.2)."""

    __tablename__ = "hitl_decision"
    __table_args__ = {"schema": SCHEMA}

    escalation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.escalation.id"))
    message_id: Mapped[uuid.UUID | None] = mapped_column()
    reviewer_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(16))  # full_accept|partial_accept|reject
    edited_answer_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    span_actions: Mapped[list | None] = mapped_column(JSONB)
    accepted_context_ids: Mapped[list | None] = mapped_column(JSONB)
    reason_code: Mapped[str | None] = mapped_column(Text)  # required for reject/partial
