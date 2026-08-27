"""`audit` schema — append-only, tamper-evident audit log (ARCH §4.6, §18; PRD-085).

The app DB role has INSERT + SELECT only on this schema (see
deploy/postgres/init/01_schemas_roles.sql). Each row stores `prev_hash` /
`row_hash` forming a chain. Query/response text is encrypted; hashes allow
correlation without decryption.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SCHEMA = "audit"


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column()
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    actor_role: Mapped[str | None] = mapped_column(String(32))
    purpose: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(
        String(32)
    )  # query|retrieval|record_access|answer|hitl_action|ingest|config_change|login
    conversation_id: Mapped[uuid.UUID | None] = mapped_column()
    patient_id: Mapped[uuid.UUID | None] = mapped_column()
    query_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    query_hash: Mapped[str | None] = mapped_column(String(64))
    retrieved: Mapped[list | None] = mapped_column(JSONB)  # [{chunk_id, score, fusion, rerank}]
    record_fields: Mapped[list | None] = mapped_column(JSONB)  # field paths returned
    model_id: Mapped[str | None] = mapped_column(String(128))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    response_text_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    grounding_summary: Mapped[dict | None] = mapped_column(JSONB)
    outcome: Mapped[str | None] = mapped_column(String(24))  # answered|escalated|no_guideline|denied
    prev_hash: Mapped[str] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSONB)
