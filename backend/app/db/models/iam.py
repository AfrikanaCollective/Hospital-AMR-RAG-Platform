"""`iam` schema — users, roles, sessions (ARCH §4.7, ARCH-011, ARCH-034).

Reviewers (rubric raters) must be clinicians: role set includes `reviewer` AND
`is_clinician` is true.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPk

SCHEMA = "iam"

ROLES = ("clinician", "reviewer", "admin", "service")


class User(UUIDPk, TimestampMixin, Base):
    __tablename__ = "user"
    __table_args__ = {"schema": SCHEMA}

    email: Mapped[str] = mapped_column(String(256), unique=True)
    display_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="active")
    is_clinician: Mapped[bool] = mapped_column(Boolean, default=False)
    # duplicate-account detection support (PRD-043) — hashed identity attributes
    identity_fingerprint: Mapped[str | None] = mapped_column(String(64))


class Role(Base):
    __tablename__ = "role"
    __table_args__ = {"schema": SCHEMA}

    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # one of ROLES


class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = {"schema": SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.user.id"), primary_key=True)
    role_code: Mapped[str] = mapped_column(ForeignKey(f"{SCHEMA}.role.code"), primary_key=True)


class ServiceAccount(UUIDPk, TimestampMixin, Base):
    __tablename__ = "service_account"
    __table_args__ = {"schema": SCHEMA}

    name: Mapped[str] = mapped_column(String(128), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64))


class Session(UUIDPk, TimestampMixin, Base):
    __tablename__ = "session"
    __table_args__ = {"schema": SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
