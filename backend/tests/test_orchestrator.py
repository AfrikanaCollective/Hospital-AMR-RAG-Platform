"""Orchestrator agent (ARCH §10.2, ARCH-025, ARCH-037)."""

from __future__ import annotations

from app.agents.orchestrator import run
from app.schemas.enums import EscalationTrigger, ObservedOutcome, ScopeLabel, SegmentType
from app.schemas.query import DISCLAIMER_TEXT


def test_scope1_query_classified_and_dispatched() -> None:
    out = run({"query": "What does the guideline recommend for a neonate with fever?"})
    assert out["scope_label"] == ScopeLabel.SCOPE_1
    assert "escalation" not in out
    assert "final_answer" not in out


def test_scope_excluded_sets_scope_boundary_escalation() -> None:
    out = run({"query": "What should I do next for this patient?", "patient_id": "p1"})
    assert out["scope_label"] == ScopeLabel.SCOPE_2_EXCLUDED
    assert out["escalation"]["trigger_code"] == EscalationTrigger.SCOPE_BOUNDARY
    assert "final_answer" not in out


def test_out_of_scope_finalizes_immediately_as_no_guideline() -> None:
    out = run({"query": "What is the hospital's parking policy?"})
    assert out["scope_label"] == ScopeLabel.OUT_OF_SCOPE
    assert out["observed_outcome"] == ObservedOutcome.NO_GUIDELINE
    assert "escalation" not in out
    assert out["final_answer"]["disclaimer"] == DISCLAIMER_TEXT


def test_second_visit_assembles_final_answer_with_disclaimer() -> None:
    state = {
        "query": "x",
        "scope_label": ScopeLabel.SCOPE_1,
        "candidate_segments": [
            {"type": SegmentType.FRAMING, "text": "Per the retrieved guideline:"},
            {
                "type": SegmentType.CLAIM,
                "text": "Guideline X recommends recording respiratory rate.",
                "citation_ids": ["c1"],
                "quote": "Record respiratory rate",
            },
        ],
        "candidate_citations": [{"citation_id": "c1"}],
    }
    out = run(state)
    assert out["final_answer"]["disclaimer"] == DISCLAIMER_TEXT
    assert out["observed_outcome"] == ObservedOutcome.WELL_SUPPORTED
    assert len(out["final_answer"]["segments"]) == 2


def test_second_visit_with_pending_escalation_does_not_finalize() -> None:
    state = {
        "query": "x",
        "scope_label": ScopeLabel.SCOPE_1,
        "escalation": {"trigger_code": EscalationTrigger.GROUNDING_FAILURE, "message": "x"},
    }
    out = run(state)
    assert "final_answer" not in out
    assert "escalation_id" not in out["escalation"]


def test_never_finalizes_once_escalation_is_persisted() -> None:
    state = {
        "query": "x",
        "scope_label": ScopeLabel.SCOPE_1,
        "escalation": {
            "trigger_code": EscalationTrigger.GROUNDING_FAILURE,
            "message": "x",
            "escalation_id": "esc-1",
        },
    }
    out = run(state)
    assert "final_answer" not in out


def test_missing_info_present_sets_missing_info_observed_outcome() -> None:
    state = {
        "query": "x",
        "scope_label": ScopeLabel.SCOPE_2_MISSING_INFO,
        "missing_info": [
            {"field": "encounter.gestational_age_weeks", "why": "x", "citation_id": "c1"}
        ],
        "candidate_segments": [
            {
                "type": SegmentType.CLAIM,
                "text": "Guideline X requires gestational age, which is missing.",
                "citation_ids": ["c1"],
                "quote": "requires gestational age",
            }
        ],
        "candidate_citations": [],
    }
    out = run(state)
    assert out["observed_outcome"] == ObservedOutcome.MISSING_INFO


def test_directive_framing_text_forces_safety_filter_escalation() -> None:
    state = {
        "query": "x",
        "scope_label": ScopeLabel.SCOPE_1,
        "candidate_segments": [
            {"type": SegmentType.FRAMING, "text": "You should start antibiotics."}
        ],
        "candidate_citations": [],
    }
    out = run(state)
    assert out["escalation"]["trigger_code"] == EscalationTrigger.SAFETY_FILTER
    assert "final_answer" not in out
