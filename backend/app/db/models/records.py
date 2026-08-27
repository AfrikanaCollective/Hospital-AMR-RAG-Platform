"""`records` schema — patient records (PHI) (ARCH §4.2; PRD-080, PRD-084).

`payload_enc` is envelope-encrypted (ARCH-032). `field_index` holds field NAMES
and null-ness only — NO values — so the missing-info agent can work without
decrypting. Row-level security (ARCH-034) restricts rows to the caller's
patient scope; enabled in the Alembic migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPk

SCHEMA = "records"


class Patient(UUIDPk, TimestampMixin, Base):
    __tablename__ = "patient"
    __table_args__ = {"schema": SCHEMA}

    mrn_enc: Mapped[bytes] = mapped_column(LargeBinary)  # encrypted synthetic MRN
    source: Mapped[str] = mapped_column(String(16))  # file | api
    consent_flags: Mapped[dict] = mapped_column(JSONB, default=dict)


class PatientRecord(UUIDPk, Base):
    """Append-only snapshot; one row per ingested record version."""

    __tablename__ = "patient_record"
    __table_args__ = {"schema": SCHEMA}

    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.patient.id"))
    schema_version: Mapped[str] = mapped_column(String(16))
    ingested_at: Mapped[datetime] = mapped_column()
    payload_enc: Mapped[bytes] = mapped_column(LargeBinary)  # envelope-encrypted JSON
    field_index: Mapped[dict] = mapped_column(JSONB, default=dict)  # names + null-ness ONLY
    source_batch_id: Mapped[uuid.UUID | None] = mapped_column()


class RecordFieldPolicy(Base):
    """(role, purpose, field_path) -> allow | deny | mask (ARCH §4.2, ARCH-034)."""

    __tablename__ = "record_field_policy"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(64))
    field_path: Mapped[str] = mapped_column(String(256))
    effect: Mapped[str] = mapped_column(String(8))  # allow | deny | mask
