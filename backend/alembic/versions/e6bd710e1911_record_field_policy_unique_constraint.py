"""record_field_policy unique constraint

Revision ID: e6bd710e1911
Revises: ba3c23a19ce9
Create Date: 2026-09-14 14:40:07.031871

`records.record_field_policy` had no uniqueness constraint on `(role,
purpose, field_path)` — `app.auth.rbac.resolve_field_effects`
(DEVIATIONS.md #87) tolerated a duplicate row by taking whichever the DB
happened to return last, rather than crashing, but that's an ambiguous
seeding-mistake state that should be impossible, not silently resolved.
Adds the constraint (ARCH-034; DEVIATIONS.md #88) so `scripts/seed_db.py`
can also do a real upsert on this table instead of insert-if-not-exists.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'e6bd710e1911'
down_revision = 'ba3c23a19ce9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_record_field_policy_role_purpose_field",
        "record_field_policy",
        ["role", "purpose", "field_path"],
        schema="records",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_record_field_policy_role_purpose_field",
        "record_field_policy",
        schema="records",
        type_="unique",
    )
