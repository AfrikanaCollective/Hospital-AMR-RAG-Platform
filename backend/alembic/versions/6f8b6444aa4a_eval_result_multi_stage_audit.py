"""eval result multi-stage audit fields

Revision ID: 6f8b6444aa4a
Revises: 9159e0f8bb84
Create Date: 2026-09-21 10:45:00.000000

Adds an audit-only, multi-stage (Phase 7 vocabulary-augmented, PRD-111 Arm C)
counterpart to each single-stage `eval.result` field (DEVIATIONS.md #186),
per operator request: "the generated Query for each [review-queue] item
should have both the single-step and multi-step (i.e. vocabulary) version."
Never rated, never read by `app.rubric.workflow` — exposed read-only by
`GET /review-queue/{id}` for traceability/comparison only.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "6f8b6444aa4a"
down_revision = "9159e0f8bb84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("result", sa.Column("multi_stage_query", sa.Text(), nullable=True), schema="eval")
    op.add_column(
        "result",
        sa.Column("multi_stage_fired", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="eval",
    )
    op.add_column(
        "result",
        sa.Column("multi_stage_answer_enc", sa.LargeBinary(), nullable=True),
        schema="eval",
    )
    op.add_column(
        "result",
        sa.Column(
            "multi_stage_citations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="eval",
    )
    op.add_column(
        "result",
        sa.Column(
            "multi_stage_retrieval_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="eval",
    )
    op.add_column(
        "result",
        sa.Column(
            "multi_stage_grounding_report",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="eval",
    )


def downgrade() -> None:
    op.drop_column("result", "multi_stage_grounding_report", schema="eval")
    op.drop_column("result", "multi_stage_retrieval_snapshot", schema="eval")
    op.drop_column("result", "multi_stage_citations", schema="eval")
    op.drop_column("result", "multi_stage_answer_enc", schema="eval")
    op.drop_column("result", "multi_stage_fired", schema="eval")
    op.drop_column("result", "multi_stage_query", schema="eval")
