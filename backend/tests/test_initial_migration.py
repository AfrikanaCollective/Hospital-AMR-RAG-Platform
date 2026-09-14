"""The real initial Alembic migration (ARCH-008; ARCH-034, ARCH-035).

Structural checks only — the migration itself is verified end-to-end against
a real (ephemeral, Dockerized) Postgres, not offline (upgrade, downgrade,
re-upgrade; RLS enforced for the restricted `hrag_app` role but not for the
migration/owner role; the audit trigger blocks UPDATE/DELETE even for the
owner). See DEVIATIONS.md #63.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

REPO = Path(__file__).resolve().parents[2]
_VERSIONS_DIR = REPO / "backend" / "alembic" / "versions"


def _migration_text() -> str:
    candidates = [
        p for p in _VERSIONS_DIR.glob("*_initial_schema.py") if p.name != "0001_initial_schema.py"
    ]
    assert len(candidates) == 1, f"expected exactly one real initial migration, found {candidates}"
    return candidates[0].read_text(encoding="utf-8")


def test_real_migration_chains_from_the_phase_1_placeholder() -> None:
    text = _migration_text()
    assert re.search(r"down_revision\s*=\s*['\"]0001_initial_schema['\"]", text)


def test_real_migration_creates_the_managed_schema_tables() -> None:
    text = _migration_text()
    for table in ("audit_event", "document", "chunk", "patient", "patient_record", "escalation"):
        assert f"op.create_table('{table}'" in text


def test_real_migration_enables_rls_on_patient_scoped_tables() -> None:
    # The DDL is built from a `_PATIENT_SCOPED_TABLES` template loop, not
    # written out per-table, so assert the template + the table list itself.
    text = _migration_text()
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "CREATE POLICY patient_scope ON" in text
    for schema, table, column in (
        ("records", "patient", "id"),
        ("records", "patient_record", "patient_id"),
        ("memory", "patient_context", "patient_id"),
    ):
        assert f'("{schema}", "{table}", "{column}")' in text or (
            f"('{schema}', '{table}', '{column}')" in text
        )


def test_real_migration_rls_policy_keys_on_the_session_guc() -> None:
    text = _migration_text()
    assert "app.current_patient_scope" in text


def test_real_migration_adds_audit_append_only_trigger() -> None:
    text = _migration_text()
    assert "BEFORE UPDATE OR DELETE ON audit.audit_event" in text
    assert "RAISE EXCEPTION" in text


def test_real_migration_does_not_manage_the_langgraph_checkpoint_table() -> None:
    text = _migration_text()
    assert "langgraph_checkpoint" not in text


def test_downgrade_reverses_rls_and_trigger_before_dropping_tables() -> None:
    text = _migration_text()
    downgrade_body = text.split("def downgrade")[1]
    assert "DROP TRIGGER IF EXISTS audit_event_no_update_delete" in downgrade_body
    assert "DROP POLICY IF EXISTS patient_scope" in downgrade_body


def test_alembic_env_uses_the_elevated_migration_url_not_the_app_runtime_url() -> None:
    env_text = (REPO / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "alembic_database_url" in env_text
    assert "get_settings().database_url" not in env_text


def test_alembic_database_url_is_a_distinct_setting_from_database_url() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.alembic_database_url != s.database_url
    assert "hrag_admin" in s.alembic_database_url
    assert "hrag_app" in s.database_url
