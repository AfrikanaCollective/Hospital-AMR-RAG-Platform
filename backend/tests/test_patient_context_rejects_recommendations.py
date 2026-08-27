"""patient_context repo rejects recommendation-shaped writes (ARCH-024; PRD-024)."""

from __future__ import annotations

import pytest

from app.memory.patient_context import (
    RecommendationShapedWriteError,
    validate_patient_context_write,
)


def test_valid_non_directive_write_ok() -> None:
    validate_patient_context_write(
        "stage_classification",
        {"stage": "stabilisation", "confidence": 0.8, "citations": ["c1"]},
    )
    validate_patient_context_write("missing_info", {"missing": ["current creatinine"]})


@pytest.mark.parametrize(
    "payload",
    [
        {"next_step": "start antibiotics"},
        {"recommendation": "escalate to HDU"},
        {"management_plan": "..."},
        {"do_next": "..."},
        {"treatment_plan": "..."},
    ],
)
def test_recommendation_shaped_payloads_rejected(payload: dict) -> None:
    with pytest.raises(RecommendationShapedWriteError):
        validate_patient_context_write("note", payload)


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError):
        validate_patient_context_write("prognosis", {"x": 1})
