"""`corpus` schema — guideline documents, versions, chunks (ARCH §4.1).

PRD-004: each chunk retains document id + version + section path + page + char
offset span. PRD-005: new versions supersede without deleting.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPk

SCHEMA = "corpus"


class Document(UUIDPk, TimestampMixin, Base):
    __tablename__ = "document"
    __table_args__ = {"schema": SCHEMA}

    external_ref: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(256))
    source_uri: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(16), default="public")  # public | internal


class DocumentVersion(UUIDPk, Base):
    __tablename__ = "document_version"
    __table_args__ = {"schema": SCHEMA}

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.document.id"))
    version_label: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[date | None] = mapped_column()
    ingested_at: Mapped[datetime] = mapped_column()
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.document_version.id")
    )
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|superseded|withdrawn
    content_sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)


class Chunk(UUIDPk, Base):
    """id == chunk_id used in citations (ARCH-014)."""

    __tablename__ = "chunk"
    __table_args__ = {"schema": SCHEMA}

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.document_version.id")
    )
    section_path: Mapped[str | None] = mapped_column(Text)
    section_number: Mapped[str | None] = mapped_column(String(32))
    heading: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey(f"{SCHEMA}.chunk.id"))
    chunk_type: Mapped[str] = mapped_column(String(16))  # prose|recommendation|table|list|criteria
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    vector_id: Mapped[str | None] = mapped_column(String(64))  # Qdrant point id
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)  # evidence grade, criteria[], topic_tags


class CorpusSnapshot(UUIDPk, TimestampMixin, Base):
    """Pinned corpus state for reproducible eval runs (PRD-072)."""

    __tablename__ = "corpus_snapshot"
    __table_args__ = {"schema": SCHEMA}

    label: Mapped[str] = mapped_column(String(64))
    embedding_collection: Mapped[str] = mapped_column(String(128))
    document_version_ids: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
