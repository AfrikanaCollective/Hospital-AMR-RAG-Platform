"""RBAC + field-level policy (ARCH-034; PRD-084, PRD-086).

- route-level: role -> permission (checked in app.api.deps.require_role),
- data-level: record_field_policy(role, purpose, field_path) -> allow|deny|mask,
- Postgres RLS on records.* and memory.patient_context keyed on the
  `app.current_patient_scope` GUC (set in app.db.session.session_scope).

Phase 4 implements resolution against the iam + records.record_field_policy
tables. The permission map is the contract.
"""

from __future__ import annotations

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


def field_allowed(effect: str) -> bool:
    return effect == "allow"


def resolve_field_effect(role: str, purpose: str, field_path: str) -> str:
    raise NotImplementedError("Phase 4: look up records.record_field_policy (ARCH-034)")
