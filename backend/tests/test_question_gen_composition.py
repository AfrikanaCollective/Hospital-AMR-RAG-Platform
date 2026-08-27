"""Auto-question set composition (ARCH §15.3; PRD-065; DEVIATIONS.md #9)."""

from __future__ import annotations

import pytest

from app.eval.question_gen.planner import Composition, allocate
from app.schemas.enums import ExpectedOutcome


def test_default_is_60_20_20_and_hard_fraction_40() -> None:
    comp = Composition.parse("60,20,20")
    assert (comp.well_supported, comp.missing_info_expected, comp.no_guideline_expected) == (60, 20, 20)
    assert comp.hard_fraction == 40  # missing_info + no_guideline


def test_hard_fraction_over_50_is_rejected() -> None:
    with pytest.raises(ValueError):
        Composition.parse("40,30,30")  # hard = 60% > 50% cap


def test_allocate_splits_total() -> None:
    got = allocate(100, Composition.parse("60,20,20"))
    assert got[ExpectedOutcome.WELL_SUPPORTED] == 60
    assert got[ExpectedOutcome.MISSING_INFO_EXPECTED] == 20
    assert got[ExpectedOutcome.NO_GUIDELINE_EXPECTED] == 20
