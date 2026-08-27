"""Scope classifier (ARCH-025).

Labels a query as one of app.schemas.enums.ScopeLabel. Deterministic first pass
(lexical intent patterns) + a constrained model classification; on ANY signal
of SCOPE-2.3 / SCOPE-2.4 intent the label is SCOPE_2_EXCLUDED and the
orchestrator escalates with trigger_code = scope_boundary (never answers).
Ambiguity resolves toward SCOPE_2_EXCLUDED / OUT_OF_SCOPE, not toward answering.

Phase 3 implements. The lexical marker lists below are the deterministic
backstop and are safe to extend.
"""

from __future__ import annotations

from app.schemas.enums import ScopeLabel

# Phrases that indicate a request to synthesize patient data + guidelines into a
# directive "what to do next" (SCOPE-2.3) — always excluded.
NEXT_STEP_MARKERS: tuple[str, ...] = (
    "what should i do next", "what should happen next", "what's the next step",
    "next step for this patient", "should i start", "should we escalate",
    "recommend for this patient", "management plan for this patient",
    "what treatment should", "which antibiotic should i give",
)

# Phrases that indicate a request to adjust a guideline for a local constraint
# beyond source text (SCOPE-2.4) — excluded unless the alternative is already in
# retrieved guideline text (SCOPE-2.5, handled downstream, not here).
LOCAL_ADAPTATION_MARKERS: tuple[str, ...] = (
    "is unavailable so what", "out of stock so", "we don't have", "substitute",
    "alternative because we can't", "swap the recommendation",
)


def classify_scope(query: str, *, has_patient: bool) -> ScopeLabel:  # noqa: ARG001
    raise NotImplementedError(
        "Phase 3: lexical backstop + constrained model classification (ARCH-025). "
        "Must return SCOPE_2_EXCLUDED on any NEXT_STEP_MARKERS / LOCAL_ADAPTATION_MARKERS hit."
    )
