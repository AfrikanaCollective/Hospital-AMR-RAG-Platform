"""Per-patient context repository (ARCH §11, ARCH-024; PRD-024).

Cross-session, structured, NON-diagnostic. Enforces:
- `kind` in the closed set (guideline_match | stage_classification |
  missing_info | note),
- NO recommendation-shaped payloads (no "next_step"/"plan"/"do"/"treat" style
  keys or free-form directive text),
- same ACL as the patient record + audit on read/write,
- no cross-patient reads (there is no API to read across patients),
- supersession via valid_to, never deletion,
- provisional -> reviewer_accepted/edited only via a HITL accept; reject rolls
  provisional entries back.

Phase 3 implements persistence; the validator below is usable now and tested.
"""

from __future__ import annotations

from app.db.models.memory import PATIENT_CONTEXT_KINDS

_FORBIDDEN_KEYS = {
    "next_step", "next_steps", "recommendation", "recommended_action", "plan",
    "management_plan", "should", "do_next", "treatment_plan", "action",
}


class RecommendationShapedWriteError(ValueError):
    """Raised when a patient_context write would constitute a recommendation (ARCH-024)."""


def validate_patient_context_write(kind: str, payload: dict) -> None:
    if kind not in PATIENT_CONTEXT_KINDS:
        raise ValueError(f"patient_context.kind must be one of {PATIENT_CONTEXT_KINDS}, got {kind!r}")
    lowered = {str(k).lower() for k in payload}
    bad = lowered & _FORBIDDEN_KEYS
    if bad:
        raise RecommendationShapedWriteError(
            f"patient_context payload contains recommendation-shaped keys {sorted(bad)} (ARCH-024)"
        )


def write_context(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Phase 3 (ARCH §11)")
