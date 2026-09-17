"""eval result answer segments

Revision ID: b05ca2378bcb
Revises: e6bd710e1911
Create Date: 2026-09-16 16:37:07.184939

`eval.result` only ever persisted the flattened answer text
(`answer_enc`) — the per-segment `citation_ids`/`grounding_note` breakdown
that `app.agents.query_pipeline` produces for a live `/query` response was
computed by `app.eval.auto_seed._build_result` and then discarded, so the
review-queue UI had no way to render a citation inline against the specific
claim it supports (only a flat answer paragraph + a separate citation list
below it, with no link between the two). Adds `answer_segments_enc`,
encrypted the same way as `answer_enc` (AES-256-GCM envelope, a distinct AAD
so the two ciphertexts are never interchangeable — `result_segments_aad`)
so the reviewer UI can reuse the same inline-citation rendering
`frontend/src/components/AnswerView.tsx` already uses for a live query.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'b05ca2378bcb'
down_revision = 'e6bd710e1911'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "result",
        sa.Column("answer_segments_enc", sa.LargeBinary(), nullable=True),
        schema="eval",
    )


def downgrade() -> None:
    op.drop_column("result", "answer_segments_enc", schema="eval")
