"""RBAC + field-level policy (ARCH-034; PRD-084, PRD-086).

- route-level: role -> permission (checked in app.api.deps.require_role),
- data-level: record_field_policy(role, purpose, field_path) -> allow|deny|mask,
- Postgres RLS on records.* and memory.patient_context keyed on the
  `app.current_patient_scope` GUC (set in app.db.session.session_scope).

`resolve_field_effects` (Phase 4, DEVIATIONS.md #87) resolves against
`records.record_field_policy`: an exact `(role, purpose, field_path)` row
wins; otherwise a `(role, purpose, "*")` wildcard row (lets an operator grant
"everything this role/purpose needs" without one row per field, then carve
out exceptions); otherwise fails **closed** to `deny` — a field is never
readable unless some policy row explicitly permits it. Callers checking
several field paths for the same `(role, purpose)` should use
`resolve_field_effects` (plural) — one query for the whole batch — rather
than calling the single-field wrapper in a loop.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models.records import RecordFieldPolicy

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# route permission -> roles allowed
ROUTE_PERMISSIONS: dict[str, frozenset[str]] = {
    "query:submit": frozenset({"clinician"}),
    "records:read": frozenset({"clinician"}),
    "ingest:documents": frozenset({"admin"}),
    "ingest:records": frozenset({"admin", "service"}),
    "hitl:decide": frozenset({"reviewer"}),
    "review_queue:read": frozenset({"reviewer"}),
    "rubric:rate": frozenset({"reviewer"}),
    "eval:manage": frozenset({"admin"}),
    "admin:all": frozenset({"admin"}),
}

# A record_field_policy row with this field_path applies to every field path
# not otherwise given its own exact-match row (DEVIATIONS.md #87).
WILDCARD_FIELD_PATH = "*"

# No matching policy row (neither exact nor wildcard) -> fail closed.
_DEFAULT_EFFECT = "deny"


def field_allowed(effect: str) -> bool:
    return effect == "allow"


def resolve_field_effects(
    session: Session, role: str, purpose: str, field_paths: Iterable[str]
) -> dict[str, str]:
    """Bulk `(role, purpose, field_path) -> allow|deny|mask` for every path in
    `field_paths`, in one query against `records.record_field_policy`."""
    paths = list(field_paths)
    if not paths:
        return {}
    rows = dict(
        session.execute(
            select(RecordFieldPolicy.field_path, RecordFieldPolicy.effect).where(
                RecordFieldPolicy.role == role,
                RecordFieldPolicy.purpose == purpose,
            )
        ).all()
    )
    wildcard_effect = rows.get(WILDCARD_FIELD_PATH, _DEFAULT_EFFECT)
    return {path: rows.get(path, wildcard_effect) for path in paths}


def resolve_field_effect(session: Session, role: str, purpose: str, field_path: str) -> str:
    """Single-field convenience wrapper around `resolve_field_effects`."""
    return resolve_field_effects(session, role, purpose, [field_path])[field_path]
