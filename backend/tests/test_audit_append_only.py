"""Audit append-only + tamper-evident chain (ARCH §18, ARCH-035; PRD-085)."""

from __future__ import annotations

from pathlib import Path

import app.audit.log as audit_log
from app.audit.log import GENESIS_HASH, canonical_row, row_hash, verify_chain, write_event
from app.db.models.audit import AuditEvent


class _FakeSession:
    """Stands in for a real DB session in offline tests: `write_event`/
    `verify_chain` only ever touch the DB through `_fetch_last_row_hash` /
    `_fetch_all_events` (monkeypatched below), so this only needs to record
    what would be inserted."""

    def __init__(self) -> None:
        self.added: list[AuditEvent] = []

    def add(self, obj: AuditEvent) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass


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


def test_write_event_chains_from_genesis_on_first_row(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    event = write_event(
        session, action="retrieval", query_hash="q1", retrieved=[{"chunk_id": "c1"}]
    )
    assert event.prev_hash == GENESIS_HASH
    assert event.row_hash != GENESIS_HASH
    assert session.added == [event]


def test_write_event_chains_from_prior_row_hash(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: "a" * 64)
    session = _FakeSession()
    event = write_event(session, action="retrieval", query_hash="q2")
    assert event.prev_hash == "a" * 64


def test_write_event_hash_changes_if_content_differs(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    e1 = write_event(_FakeSession(), action="retrieval", query_hash="same-prev-hash-input")
    e2 = write_event(_FakeSession(), action="retrieval", query_hash="different")
    assert e1.row_hash != e2.row_hash


def test_verify_chain_reports_no_breaks_for_an_intact_chain(monkeypatch) -> None:  # noqa: ANN001
    e1 = AuditEvent(id=1, ts="t1", action="retrieval", prev_hash=GENESIS_HASH)
    e1.row_hash = row_hash(
        {f: getattr(e1, f, None) for f in audit_log._HASHED_FIELDS}, GENESIS_HASH
    )
    e2 = AuditEvent(id=2, ts="t2", action="retrieval", prev_hash=e1.row_hash)
    e2.row_hash = row_hash({f: getattr(e2, f, None) for f in audit_log._HASHED_FIELDS}, e1.row_hash)
    monkeypatch.setattr(audit_log, "_fetch_all_events", lambda session: [e1, e2])
    assert verify_chain(_FakeSession()) == []


def test_verify_chain_detects_a_tampered_row(monkeypatch) -> None:  # noqa: ANN001
    e1 = AuditEvent(id=1, ts="t1", action="retrieval", prev_hash=GENESIS_HASH)
    e1.row_hash = row_hash(
        {f: getattr(e1, f, None) for f in audit_log._HASHED_FIELDS}, GENESIS_HASH
    )
    e2 = AuditEvent(id=2, ts="t2", action="retrieval", prev_hash=e1.row_hash)
    e2.row_hash = row_hash({f: getattr(e2, f, None) for f in audit_log._HASHED_FIELDS}, e1.row_hash)
    e1.action = (
        "record_access"  # tamper with row 1's content only, leaving its stored row_hash stale
    )
    monkeypatch.setattr(audit_log, "_fetch_all_events", lambda session: [e1, e2])
    # row 1's stored hash no longer matches a recompute of its (now-tampered)
    # content -> flagged directly. Row 2 is untouched and its prev_hash still
    # matches row 1's (unchanged) *stored* row_hash, so it stays internally
    # consistent — cascading the tamper to row 2 too would require also
    # rewriting row 2's prev_hash/row_hash, which is exactly the larger,
    # easier-to-notice operation a hash chain is meant to force. The app DB
    # role can't run UPDATE on this schema at all regardless (ARCH-035).
    assert verify_chain(_FakeSession()) == [1]


def test_postgres_init_sql_revokes_update_delete_on_audit() -> None:
    sql = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "postgres"
        / "init"
        / "01_schemas_roles.sql"
    ).read_text()
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM hrag_app" in sql
    # audit gets INSERT + SELECT only
    assert "GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA audit TO hrag_app" in sql
