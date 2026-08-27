"""Escalation lifecycle (ARCH §12.2).

open -> in_review -> resolved (accepted | partial | rejected). All transitions
audit-logged. No reviewer within ESCALATION_SLA_MINUTES => stays open, user
sees a held state + safe templated message, NOT auto-released (DEVIATIONS.md #14).
Phase 3.
"""

from __future__ import annotations

HELD_TEMPLATE = (
    "This response needs clinician review before it can be shown. "
    "No independent recommendation is available from the system."
)


def create_escalation(*_args: object, **_kwargs: object) -> str:
    raise NotImplementedError("Phase 3 (ARCH §12.2)")
