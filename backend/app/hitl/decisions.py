"""Accept-axis effects on state (ARCH §13.2; PRD-032).

full_accept / partial_accept / reject and what each does to: the shown answer,
conversation memory, patient_context, escalation/eval, and audit. This module
is the single place those effects are applied so they stay consistent with the
table in ARCHITECTURE.md §13.2.

Phase 3 implements. The mapping below is the contract.
"""

from __future__ import annotations

from app.schemas.enums import HitlAcceptAction

# Summary of ARCH §13.2 — used by tests and by the implementation.
EFFECTS: dict[str, dict[str, str]] = {
    HitlAcceptAction.FULL_ACCEPT: {
        "shown_answer": "released as-is; marked validated",
        "conversation_memory": "assistant turn committed as accepted",
        "patient_context": "provisional entries -> reviewer_accepted",
        "escalation": "resolution=accepted, state=resolved",
    },
    HitlAcceptAction.PARTIAL_ACCEPT: {
        "shown_answer": "reviewer-edited version canonical; original + diff kept",
        "conversation_memory": "edited turn committed, linked to original; removed spans logged as failures",
        "patient_context": "only retained entries -> reviewer_edited; rest expired",
        "escalation": "resolution=partial; reason_code required",
    },
    HitlAcceptAction.REJECT: {
        "shown_answer": "not released / retracted; safe fallback shown",
        "conversation_memory": "rejected turn (question kept, body = rejection notice + reason_code)",
        "patient_context": "ALL provisional entries for this result rolled back (valid_to=now)",
        "escalation": "resolution=rejected; reason_code required; flagged as eval failure",
    },
}


def apply_decision(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Phase 3 (ARCH §13.2)")
