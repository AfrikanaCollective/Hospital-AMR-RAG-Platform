"""Shared enums used across the API and data model.

Kept in one place because several of these are safety-relevant and referenced
by tests (scope boundary, expected-outcome scoring, HITL effects).
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    """PRD-045 — visible everywhere a result appears in the rubric workflow."""

    AUTO_GENERATED = "auto_generated"
    CLINICIAN_SUBMITTED = "clinician_submitted"


class ExpectedOutcome(StrEnum):
    """PRD-063 — separate from and additional to Provenance.

    Composition target 60/20/20 (PRD-065). Hard cases = MISSING_INFO_EXPECTED +
    NO_GUIDELINE_EXPECTED (DEVIATIONS.md #9), must not exceed 50%.
    """

    WELL_SUPPORTED = "well_supported"
    MISSING_INFO_EXPECTED = "missing_info_expected"
    NO_GUIDELINE_EXPECTED = "no_guideline_expected"


class ObservedOutcome(StrEnum):
    """What the pipeline actually did (ARCH §4.5 result.observed_outcome)."""

    WELL_SUPPORTED = "well_supported"
    MISSING_INFO = "missing_info"
    NO_GUIDELINE = "no_guideline"
    ESCALATED = "escalated"


class ScopeLabel(StrEnum):
    """Orchestrator scope classification (ARCH-025)."""

    SCOPE_1 = "scope_1"  # grounded guideline reporting/synthesis
    SCOPE_2_STAGE = "scope_2_stage"  # SCOPE-2.1 stage classification
    SCOPE_2_MISSING_INFO = "scope_2_missing_info"  # SCOPE-2.2
    SCOPE_2_EXCLUDED = "scope_2_excluded"  # SCOPE-2.3 / SCOPE-2.4 -> always escalate, never answer
    OUT_OF_SCOPE = "out_of_scope"  # cohort/other -> reject


class SegmentType(StrEnum):
    CLAIM = "claim"  # statement about guideline content; >= 1 citation + verbatim quote
    FRAMING = "framing"  # non-claim connective text; no directive phrasing


class GroundingVerdict(StrEnum):
    SUPPORTED = "supported"
    WEAK = "weak"
    UNSUPPORTED = "unsupported"


class HitlAcceptAction(StrEnum):
    """ARCH §13.2 — accept axis (independent of rank mode)."""

    FULL_ACCEPT = "full_accept"
    PARTIAL_ACCEPT = "partial_accept"
    REJECT = "reject"


class EscalationTrigger(StrEnum):
    """ARCH §12.1 — canonical escalation trigger codes."""

    LOW_CONFIDENCE = "low_confidence"
    NO_GUIDELINE = "no_guideline"  # terminal, not held
    GROUNDING_FAILURE = "grounding_failure"
    WEAK_SUPPORT = "weak_support"  # soft: released + queued
    CONFLICTING_SOURCES = "conflicting_sources"
    USER_REQUESTED = "user_requested"
    PHI_AMBIGUITY = "phi_ambiguity"
    SCOPE_BOUNDARY = "scope_boundary"  # SCOPE-2.3/2.4 or directive wording; never answered
    LOCAL_CONSTRAINT_NO_SOURCE_ALT = "local_constraint_no_source_alt"  # SCOPE-2.5 fallthrough
    CAPABILITY_NOT_ENABLED = "capability_not_enabled"  # local-adaptation stub reached
    STAGE_CLASSIFICATION_UNCERTAIN = "stage_classification_uncertain"
    MISSING_CRITICAL_INFO = "missing_critical_info"
    SAFETY_FILTER = "safety_filter"
    REVIEW_SAMPLING = "review_sampling"  # released + queued


class DocumentVersionStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"
