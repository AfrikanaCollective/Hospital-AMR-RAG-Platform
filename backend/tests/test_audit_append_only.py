"""Audit append-only + tamper-evident chain (ARCH §18, ARCH-035; PRD-085)."""

from __future__ import annotations

from pathlib import Path

from app.audit.log import GENESIS_HASH, canonical_row, row_hash


def test_row_hash_is_deterministic_and_chains() -> None:
    r1 = {"id": 1, "action": "query", "ts": "2026-08-27T00:00:00Z"}
    h1 = row_hash(r1, GENESIS_HASH)
    assert h1 == row_hash(r1, GENESIS_HASH)  # deterministic

    r2 = {"id": 2, "action": "answer", "ts": "2026-08-27T00:00:01Z"}
    h2 = row_hash(r2, h1)
    # a change in the earlier row breaks every subsequent hash
    r1_tampered = {**r1, "action": "record_access"}
    assert row_hash(r2, row_hash(r1_tampered, GENESIS_HASH)) != h2


def test_canonical_row_is_key_order_independent() -> None:
    assert canonical_row({"a": 1, "b": 2}) == canonical_row({"b": 2, "a": 1})


def test_postgres_init_sql_revokes_update_delete_on_audit() -> None:
    sql = (
        Path(__file__).resolve().parents[2]
        / "deploy" / "postgres" / "init" / "01_schemas_roles.sql"
    ).read_text()
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM hrag_app" in sql
    # audit gets INSERT + SELECT only
    assert "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA audit TO hrag_app" in sql
