"""Audit writer (ARCH §18, ARCH-035; PRD-085).

- one `audit.audit_event` per: query, retrieval (chunks + scores), record
  access (field list), answer (model id, response hash, grounding summary,
  outcome), HITL action, ingest, config change, login;
- INSERT only (the DB role has no UPDATE/DELETE on the audit schema);
- `prev_hash`/`row_hash` chain for tamper evidence;
- query/response text encrypted (CryptoProvider); `query_hash`/`response_hash`
  in plaintext for correlation without decryption.

**Scope of this implementation (DEVIATIONS.md #50):** `write_event`/`verify_chain`
work for any `AuditEvent` action today — the function is generic — but only the
`retrieval` action actually has a caller yet (`app.retrieval.hybrid.retrieve`).
Callers for `answer`/`hitl_action`/`login`/`config_change` land in their
respective phases (3/4) along with the code that produces those events; a
scheduled chain-verifier *job* (as opposed to the `verify_chain` function
itself, usable today) is also Phase 4.

`_fetch_last_row_hash`/`_fetch_all_events` are the only two points that touch
the database — indirection so tests exercise the real hashing/chaining logic
with a trivial fake session, without needing a real Postgres (JSONB columns
don't compile against SQLite, and unit tests must stay offline, CLAUDE.md §5).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text

from app.db.models.audit import AuditEvent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

GENESIS_HASH = "0" * 64

# The row's own content, hashed together with the previous row's hash. Every
# AuditEvent column except the identity/chain columns themselves (id,
# prev_hash, row_hash) — those either aren't known until the row exists or
# would make the hash circular.
_HASHED_FIELDS = (
    "ts",
    "actor_id",
    "actor_role",
    "purpose",
    "action",
    "conversation_id",
    "patient_id",
    "query_text_enc",
    "query_hash",
    "retrieved",
    "record_fields",
    "model_id",
    "response_hash",
    "response_text_enc",
    "grounding_summary",
    "outcome",
    "detail",
)


def canonical_row(fields: dict) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def row_hash(fields: dict, prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + canonical_row(fields)).encode("utf-8")).hexdigest()


def _row_fields(event: AuditEvent) -> dict[str, Any]:
    return {f: getattr(event, f) for f in _HASHED_FIELDS}


# Arbitrary, stable lock key for the audit-chain advisory lock (DEVIATIONS.md
# #95). Any fixed 64-bit signed int works; this one just spells something
# recognizable in hex. Never change it — a running deployment mid-upgrade
# would stop actually serializing against itself.
_CHAIN_LOCK_KEY = 0x4155_4449_544C_4F47  # "AUDITLOG" in ASCII hex, truncated to fit


def _fetch_last_row_hash(session: Session) -> str | None:
    # A Postgres session-transaction advisory lock (DEVIATIONS.md #95) —
    # NOT `SELECT ... FOR UPDATE` on the last row, which was tried first and
    # verified NOT to work: locking an existing row only blocks a second
    # transaction from also locking that SAME row, but a fresh INSERT never
    # modifies that row, so once the lock holder commits, everyone else
    # blocked on it wakes up and proceeds with the now-stale row they'd
    # already planned to use — confirmed by a real concurrent-writer test
    # against a real Postgres that still produced a broken chain with that
    # approach. An advisory lock instead serializes the whole read-last-hash
    # + insert-new-row sequence itself, for every caller, regardless of
    # which row anyone reads: `pg_advisory_xact_lock` blocks until acquired
    # and auto-releases at COMMIT/ROLLBACK — exactly `write_event`'s own
    # transaction lifetime (`session_scope()`).
    #
    # This is a real, not hypothetical, race: `POST /query`'s own `get_db()`
    # session writes the `query` event while, moments later,
    # `app.retrieval.hybrid.retrieve` (called from deep inside the graph
    # run, on its own separate session) writes `retrieval` and commits
    # independently, before the outer request session commits — both could
    # read the same "last row" and produce two rows sharing one `prev_hash`.
    # Found via a real docker-compose end-to-end run, then reproduced
    # directly with 8 concurrent writers against a real Postgres; fixed the
    # same way, verified with the same repro (broken chain -> no breaks).
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _CHAIN_LOCK_KEY})
    return session.execute(
        select(AuditEvent.row_hash).order_by(AuditEvent.id.desc()).limit(1)
    ).scalar_one_or_none()


def _fetch_all_events(session: Session) -> list[AuditEvent]:
    return list(session.execute(select(AuditEvent).order_by(AuditEvent.id.asc())).scalars().all())


def write_event(
    session: Session,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    purpose: str | None = None,
    conversation_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    query_text_enc: bytes | None = None,
    query_hash: str | None = None,
    retrieved: list | None = None,
    record_fields: list | None = None,
    model_id: str | None = None,
    response_hash: str | None = None,
    response_text_enc: bytes | None = None,
    grounding_summary: dict | None = None,
    outcome: str | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    """Append one audit row, chained to the previous one. INSERT-only: never
    call this to correct a past row — log a new corrective event instead."""
    prev_hash = _fetch_last_row_hash(session) or GENESIS_HASH
    event = AuditEvent(
        ts=datetime.now(UTC),
        actor_id=actor_id,
        actor_role=actor_role,
        purpose=purpose,
        action=action,
        conversation_id=conversation_id,
        patient_id=patient_id,
        query_text_enc=query_text_enc,
        query_hash=query_hash,
        retrieved=retrieved,
        record_fields=record_fields,
        model_id=model_id,
        response_hash=response_hash,
        response_text_enc=response_text_enc,
        grounding_summary=grounding_summary,
        outcome=outcome,
        prev_hash=prev_hash,
        row_hash=GENESIS_HASH,  # placeholder; replaced below once fields are set
        detail=detail,
    )
    event.row_hash = row_hash(_row_fields(event), prev_hash)
    session.add(event)
    session.flush()
    return event


_MAX_QUERY_LIMIT = 200


def query_events(
    session: Session,
    *,
    action: str | None = None,
    patient_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[AuditEvent]:
    """Most-recent-first, optionally filtered by exact `action`/`patient_id`/
    `actor_id`. Backs `GET /admin/audit` (ARCH-035). `limit` is capped at
    `_MAX_QUERY_LIMIT` regardless of what's requested — an unbounded audit
    query is its own kind of footgun on a table that only ever grows."""
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit, _MAX_QUERY_LIMIT))
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if patient_id is not None:
        stmt = stmt.where(AuditEvent.patient_id == patient_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    return list(session.execute(stmt).scalars().all())


def verify_chain(session: Session) -> list[int]:
    """Return the ids of rows where the chain is broken (empty => intact)."""
    broken: list[int] = []
    prev_hash = GENESIS_HASH
    for row in _fetch_all_events(session):
        expected = row_hash(_row_fields(row), prev_hash)
        if row.prev_hash != prev_hash or row.row_hash != expected:
            broken.append(row.id)
        prev_hash = row.row_hash
    return broken
