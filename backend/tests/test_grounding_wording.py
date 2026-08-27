"""Deterministic wording filter (ARCH §8.3 step 4; SCOPE-1.2, PRD-088)."""

from __future__ import annotations

import pytest

from app.grounding.wording import has_directive_phrasing, scan_segment


@pytest.mark.parametrize(
    "text",
    [
        "You should start antibiotics now.",
        "We recommend that you escalate to HDU.",
        "The next step for this patient is a CT scan.",
        "I recommend apixaban.",
    ],
)
def test_directive_phrasing_flagged(text: str) -> None:
    assert has_directive_phrasing(text)
    assert "directive_phrasing" in scan_segment(text, cited_quotes=[])


@pytest.mark.parametrize(
    "text",
    [
        "Guideline 001 recommends recording respiratory rate at presentation.",
        "Per the retrieved source, supplemental oxygen is recommended to a documented target.",
        "The guideline does not document an alternative for this scenario.",
    ],
)
def test_reported_content_not_flagged(text: str) -> None:
    assert not has_directive_phrasing(text)
    assert scan_segment(text, cited_quotes=[]) == []
