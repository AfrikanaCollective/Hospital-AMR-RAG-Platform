"""initial schema (placeholder)

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-27

Phase 1 placeholder. The real initial migration is generated in Phase 2 with:

    alembic revision --autogenerate -m "initial schema"

against the models in app/db/models/ (schemas: corpus, records, memory, hitl,
eval, audit, iam). That migration must ALSO:
  - enable row-level security on records.* and memory.patient_context and add
    policies keyed on the `app.current_patient_scope` GUC (ARCH-034),
  - add the audit-schema trigger/rule that rejects UPDATE/DELETE as defense in
    depth beyond the role GRANTs (ARCH-035),
  - create the langgraph checkpoint tables via the library's setup, or leave
    them to the checkpointer's own migration.
Do not hand-maintain DDL here once autogenerate is wired.
"""

from __future__ import annotations

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally empty in Phase 1. See module docstring.
    pass


def downgrade() -> None:
    pass
