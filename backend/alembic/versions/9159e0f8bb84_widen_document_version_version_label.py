"""widen document_version.version_label

Revision ID: 9159e0f8bb84
Revises: b05ca2378bcb
Create Date: 2026-09-21 05:40:00.000000

`corpus.document_version.version_label` was `String(64)` — too narrow for a
real, verbatim-quoted version label (ARCH-038: metadata is drafted from the
document's own imprint page, never invented/shortened). Found only by real
data, not by any offline test: the WHO SBI 2024 document's own corrigenda
notice ("2024, corrigenda of 25 March 2025 incorporated into this electronic
file", 72 chars) has sat in `data/excerpt_guidelines/manifest.json` since an
earlier session, but nothing ever actually drove ingestion from the manifest
until `scripts/ingest_manifest_documents.py` (DEVIATIONS.md #174) — the
insert failed with `StringDataRightTruncation` on first real use. Widened to
256, matching `document.publisher`'s width, rather than truncating or
paraphrasing a real, sourced value to fit an arbitrary limit.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '9159e0f8bb84'
down_revision = 'b05ca2378bcb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "document_version",
        "version_label",
        type_=sa.String(length=256),
        existing_type=sa.String(length=64),
        existing_nullable=False,
        schema="corpus",
    )


def downgrade() -> None:
    op.alter_column(
        "document_version",
        "version_label",
        type_=sa.String(length=64),
        existing_type=sa.String(length=256),
        existing_nullable=False,
        schema="corpus",
    )
