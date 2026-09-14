"""Scope classifier (ARCH-025; DEVIATIONS.md #68)."""

from __future__ import annotations

import pytest

from app.schemas.enums import ScopeLabel
from app.scope.classifier import classify_scope


@pytest.mark.parametrize(
    "query",
    [
        "What should I do next for this patient?",
        "What's the next step for this patient with a fever?",
        "Which antibiotic should I give?",
        "The recommended drug is unavailable so what should we substitute?",
        "We don't have gentamicin, what alternative should we use?",
    ],
)
def test_excluded_markers_always_win(query: str) -> None:
    assert classify_scope(query, has_patient=True) == ScopeLabel.SCOPE_2_EXCLUDED
    assert classify_scope(query, has_patient=False) == ScopeLabel.SCOPE_2_EXCLUDED


def test_excluded_wins_over_guideline_phrasing() -> None:
    query = "What does the guideline recommend as the next step for this patient?"
    assert classify_scope(query, has_patient=True) == ScopeLabel.SCOPE_2_EXCLUDED


def test_scope1_guideline_lookup() -> None:
    query = "What does the guideline recommend for a neonate presenting with fever?"
    assert classify_scope(query, has_patient=False) == ScopeLabel.SCOPE_1
    assert classify_scope(query, has_patient=True) == ScopeLabel.SCOPE_1


def test_stage_classification_requires_patient() -> None:
    query = "What stage of care is this patient in?"
    assert classify_scope(query, has_patient=True) == ScopeLabel.SCOPE_2_STAGE
    assert classify_scope(query, has_patient=False) == ScopeLabel.OUT_OF_SCOPE


def test_missing_info_requires_patient() -> None:
    query = "What information is missing from this patient's record?"
    assert classify_scope(query, has_patient=True) == ScopeLabel.SCOPE_2_MISSING_INFO
    assert classify_scope(query, has_patient=False) == ScopeLabel.OUT_OF_SCOPE


def test_out_of_scope_default() -> None:
    assert classify_scope("What is the hospital's parking policy?", has_patient=False) == (
        ScopeLabel.OUT_OF_SCOPE
    )
