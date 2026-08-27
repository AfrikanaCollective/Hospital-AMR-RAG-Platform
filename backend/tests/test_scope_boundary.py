"""Hard CDS boundary (SCOPE-2.3 / SCOPE-2.4; CDS-FUTURE.md).

Phase 1 asserts the *contract*: the excluded stubs contain no logic, the
reserved role is not in the runtime graph, the never-answered trigger set is
correct, and the excluded feature flag is inert. The behavioural test (a
SCOPE-2.3/2.4 prompt -> escalation, zero recommendation) lands in Phase 3 and
is a build-gating test then.
"""

from __future__ import annotations

import pytest

from app.hitl.triggers import NEVER_ANSWERED
from app.schemas.enums import EscalationTrigger


def test_never_answered_triggers() -> None:
    assert EscalationTrigger.SCOPE_BOUNDARY in NEVER_ANSWERED
    assert EscalationTrigger.CAPABILITY_NOT_ENABLED in NEVER_ANSWERED


def test_local_adaptation_flag_is_inert_and_agent_only_escalates(settings) -> None:  # noqa: ANN001
    assert settings.local_adaptation_enabled is False
    from app.agents.local_adaptation_agent import run

    state: dict = {}
    out = run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.CAPABILITY_NOT_ENABLED


def test_next_step_recommender_has_no_implementation() -> None:
    from app.agents.next_step_recommender import recommend_next_step

    with pytest.raises(NotImplementedError):
        recommend_next_step(object())


def test_excluded_agent_sources_carry_the_governance_marker() -> None:
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "app" / "agents"
    for name in ("local_adaptation_agent.py", "next_step_recommender.py"):
        text = (base / name).read_text()
        assert "DO NOT IMPLEMENT WITHOUT GOVERNANCE GATE" in text
        assert "CDS-FUTURE.md" in text


def test_scope_classifier_marker_lists_present() -> None:
    from app.scope.classifier import LOCAL_ADAPTATION_MARKERS, NEXT_STEP_MARKERS

    assert any("next step" in m for m in NEXT_STEP_MARKERS)
    assert NEXT_STEP_MARKERS and LOCAL_ADAPTATION_MARKERS
