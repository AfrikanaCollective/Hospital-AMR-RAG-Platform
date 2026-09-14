"""Escalation trigger metadata (ARCH §12.1).

The canonical codes are app.schemas.enums.EscalationTrigger. This table records,
per trigger, whether a candidate answer may be released (held vs released vs
never-answered) so the orchestrator and tests share one source of truth.
"""

from __future__ import annotations

from app.schemas.enums import EscalationTrigger as T

# release_policy: "held" | "released_and_queued" | "never_answered" | "terminal_no_guideline"
RELEASE_POLICY: dict[str, str] = {
    T.LOW_CONFIDENCE: "held",
    T.NO_GUIDELINE: "terminal_no_guideline",
    T.GROUNDING_FAILURE: "held",
    T.WEAK_SUPPORT: "released_and_queued",
    T.CONFLICTING_SOURCES: "held",
    T.USER_REQUESTED: "released_and_queued",
    T.PHI_AMBIGUITY: "held",
    T.SCOPE_BOUNDARY: "never_answered",
    T.LOCAL_CONSTRAINT_NO_SOURCE_ALT: "held",
    T.CAPABILITY_NOT_ENABLED: "never_answered",
    T.STAGE_CLASSIFICATION_UNCERTAIN: "held",
    T.MISSING_CRITICAL_INFO: "held",
    T.SAFETY_FILTER: "held",
    T.REVIEW_SAMPLING: "released_and_queued",
}

# Triggers that must NEVER yield an answer, ever (SCOPE boundary + capability stub).
NEVER_ANSWERED: frozenset[str] = frozenset({T.SCOPE_BOUNDARY, T.CAPABILITY_NOT_ENABLED})
