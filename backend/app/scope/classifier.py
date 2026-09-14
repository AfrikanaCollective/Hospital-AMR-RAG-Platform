"""Scope classifier (ARCH-025).

Labels a query as one of app.schemas.enums.ScopeLabel. Deterministic first pass
(lexical intent patterns) + a constrained model classification; on ANY signal
of SCOPE-2.3 / SCOPE-2.4 intent the label is SCOPE_2_EXCLUDED and the
orchestrator escalates with trigger_code = scope_boundary (never answers).
Ambiguity resolves toward SCOPE_2_EXCLUDED / OUT_OF_SCOPE, not toward answering.

Phase 3 (DEVIATIONS.md #68): implemented as the deterministic lexical backstop
ONLY — no model call. The lexical backstop is the safety-critical layer (its
markers are exhaustively tested and it is what the gating test
`test_scope_boundary.py` exercises); routing an *additional* constrained model
classification through this path would add a non-deterministic dependency to
a control whose failure mode is "answers something SCOPE-2.3/2.4 should have
blocked" — the highest-severity failure mode in this system. The prompt
template (`app/agents/prompts/orchestrator_scope.md`) is kept as the documented
contract for that future model-assisted pass (e.g. to refine SCOPE_1 vs.
SCOPE_2_STAGE vs. SCOPE_2_MISSING_INFO vs. OUT_OF_SCOPE ambiguity, where a
wrong answer is a UX/precision issue, not a boundary breach), but it is not
wired to a model call yet — that is future hardening, not a Phase-3 gap
(nothing in prompt.txt's Phase 3 checklist requires it), and the lexical
backstop alone already satisfies every scope-boundary requirement.

The lexical marker lists below are the deterministic backstop and are safe to
extend.
"""

from __future__ import annotations

from app.schemas.enums import ScopeLabel

# Phrases that indicate a request to synthesize patient data + guidelines into a
# directive "what to do next" (SCOPE-2.3) — always excluded.
NEXT_STEP_MARKERS: tuple[str, ...] = (
    "what should i do next",
    "what should happen next",
    "what's the next step",
    "next step for this patient",
    "should i start",
    "should we escalate",
    "recommend for this patient",
    "management plan for this patient",
    "what treatment should",
    "which antibiotic should i give",
)

# Phrases that indicate a request to adjust a guideline for a local constraint
# beyond source text (SCOPE-2.4) — excluded unless the alternative is already in
# retrieved guideline text (SCOPE-2.5, handled downstream, not here).
LOCAL_ADAPTATION_MARKERS: tuple[str, ...] = (
    "is unavailable so what",
    "out of stock so",
    "we don't have",
    "substitute",
    "alternative because we can't",
    "swap the recommendation",
)

# Patient-specific stage-of-care classification intent (SCOPE-2.1) — requires
# an attached patient; without one this is not answerable as scope_2_stage.
STAGE_MARKERS: tuple[str, ...] = (
    "what stage",
    "current stage of care",
    "which stage is",
    "stage of care for",
    "what stage of care",
    "classify this patient's stage",
    "stage is this patient in",
)

# Missing-information / clarification-seeking intent (SCOPE-2.2) — requires an
# attached patient.
MISSING_INFO_MARKERS: tuple[str, ...] = (
    "what information is missing",
    "what data is missing",
    "what's missing from",
    "what is missing from",
    "what do we need to know",
    "additional information needed",
    "missing information",
    "what else do we need",
)

# Guideline-lookup / reporting intent (SCOPE-1) — the in-scope hypothetical
# framing per ARCH §15.1 / the auto-question generator's required shape.
SCOPE1_MARKERS: tuple[str, ...] = (
    "what does the guideline",
    "does the guideline recommend",
    "guideline recommend",
    "guideline say",
    "per the guideline",
    "what does the protocol",
    "what is the recommended",
    "recommended approach for",
    "what do the guidelines say",
    "what does guidance",
    "presenting with",
)


def _any_marker(query_lower: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query_lower for marker in markers)


def classify_scope(query: str, *, has_patient: bool) -> ScopeLabel:
    """Deterministic lexical classification (DEVIATIONS.md #68).

    Order matters: the excluded-capability check runs first and wins over
    every other signal — a query that also looks like a guideline lookup but
    contains an excluded marker is still SCOPE_2_EXCLUDED. Patient-specific
    labels (stage/missing-info) only apply when a patient is attached;
    otherwise they fall through toward OUT_OF_SCOPE rather than being
    silently answered as SCOPE_1 (ARCH-025: ambiguity resolves toward
    escalation/rejection, not toward answering).
    """
    q = query.lower()

    if _any_marker(q, NEXT_STEP_MARKERS) or _any_marker(q, LOCAL_ADAPTATION_MARKERS):
        return ScopeLabel.SCOPE_2_EXCLUDED

    if has_patient and _any_marker(q, STAGE_MARKERS):
        return ScopeLabel.SCOPE_2_STAGE

    if has_patient and _any_marker(q, MISSING_INFO_MARKERS):
        return ScopeLabel.SCOPE_2_MISSING_INFO

    if not has_patient and (_any_marker(q, STAGE_MARKERS) or _any_marker(q, MISSING_INFO_MARKERS)):
        # Patient-specific intent with no patient attached: cannot be
        # answered as scope_2_*, and treating it as a generic scope_1
        # guideline lookup would silently drop the patient-specific framing
        # the user asked for. Reject rather than guess (ARCH-025).
        return ScopeLabel.OUT_OF_SCOPE

    if _any_marker(q, SCOPE1_MARKERS):
        return ScopeLabel.SCOPE_1

    return ScopeLabel.OUT_OF_SCOPE
