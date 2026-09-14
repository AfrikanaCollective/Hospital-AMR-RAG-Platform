"""LangGraph topology + routing (ARCH §10.1).

Uses a real, in-process `MemorySaver` checkpointer (no Postgres) and the real
`orchestrator` node (routing depends on exactly what it writes to state), but
fakes every other node so this test exercises graph WIRING, not agent
internals — those are covered by each agent's own test module.
"""

from __future__ import annotations

import pytest

import app.agents.citation_verifier_agent as cva
import app.agents.guideline_synthesis_agent as gsa
import app.agents.missing_info_agent as mia
import app.agents.patient_record_agent as pra
import app.agents.retrieval_agent as ra
import app.agents.stage_classifier_agent as sca
from app.agents.graph import EDGES, NODES, build_graph
from app.schemas.enums import EscalationTrigger, ScopeLabel


def test_node_and_edge_contract_unchanged() -> None:
    assert set(NODES) == {
        "orchestrator",
        "retrieval",
        "patient_record",
        "stage_classifier",
        "missing_info",
        "guideline_synthesis",
        "citation_verifier",
        "escalation",
        "local_adaptation",
    }
    assert ("citation_verifier", "orchestrator") in EDGES
    assert ("citation_verifier", "escalation") in EDGES
    assert "local_adaptation" not in {a for a, _ in EDGES} | {b for _, b in EDGES}


@pytest.fixture
def graph(monkeypatch):  # noqa: ANN001
    from langgraph.checkpoint.memory import MemorySaver

    monkeypatch.setattr(
        ra,
        "run",
        lambda s: {
            **s,
            "retrieval": [{"chunk_id": "ch1"}],
            "retrieval_confidence": {
                "essentially_empty": False,
                "low_confidence": False,
                "conflicts": [],
            },
        },
    )
    monkeypatch.setattr(
        gsa,
        "run",
        lambda s: (
            s
            if s.get("escalation")
            else {
                **s,
                "candidate_segments": [{"type": "framing", "text": "ok"}],
                "candidate_citations": [],
            }
        ),
    )
    monkeypatch.setattr(cva, "run", lambda s: s)
    monkeypatch.setattr(
        pra,
        "run",
        lambda s: (
            {**s, "patient_features": {}}
            if s.get("patient_id")
            else {
                **s,
                "escalation": {
                    "trigger_code": EscalationTrigger.PHI_AMBIGUITY,
                    "message": "no patient",
                },
            }
        ),
    )
    monkeypatch.setattr(
        sca, "run", lambda s: {**s, "stage_classification": {"stage": "A", "uncertain": False}}
    )
    monkeypatch.setattr(mia, "run", lambda s: {**s, "missing_info": [{"field": "x"}]})

    def _fake_escalation_run(s):  # noqa: ANN001, ANN202
        esc = dict(s["escalation"])
        esc["escalation_id"] = "esc-fake-1"
        return {**s, "escalation": esc}

    import app.agents.escalation_agent as eac

    monkeypatch.setattr(eac, "run", _fake_escalation_run)

    return build_graph(checkpointer=MemorySaver())


def test_scope1_happy_path_reaches_final_answer(graph) -> None:  # noqa: ANN001
    out = graph.invoke(
        {"query": "What does the guideline recommend for fever?"},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert out["scope_label"] == ScopeLabel.SCOPE_1
    assert "final_answer" in out
    assert "escalation" not in out


def test_scope_excluded_routes_straight_to_escalation(graph) -> None:  # noqa: ANN001
    out = graph.invoke(
        {"query": "What should I do next for this patient?", "patient_id": "p1"},
        config={"configurable": {"thread_id": "t2"}},
    )
    assert out["scope_label"] == ScopeLabel.SCOPE_2_EXCLUDED
    assert out["escalation"]["trigger_code"] == EscalationTrigger.SCOPE_BOUNDARY
    assert out["escalation"]["escalation_id"] == "esc-fake-1"
    assert "final_answer" not in out


def test_scope2_stage_happy_path_reaches_final_answer(graph) -> None:  # noqa: ANN001
    out = graph.invoke(
        {"query": "What stage of care is this patient in?", "patient_id": "p1"},
        config={"configurable": {"thread_id": "t3"}},
    )
    assert out["scope_label"] == ScopeLabel.SCOPE_2_STAGE
    assert out["stage_classification"]["stage"] == "A"
    assert "final_answer" in out


def test_scope2_missing_info_is_released_not_escalated(graph) -> None:  # noqa: ANN001
    # SCOPE-2.2 is clarification-seeking, not a HITL hold (DEVIATIONS.md #76).
    out = graph.invoke(
        {"query": "What information is missing from this patient's record?", "patient_id": "p1"},
        config={"configurable": {"thread_id": "t4"}},
    )
    assert out["scope_label"] == ScopeLabel.SCOPE_2_MISSING_INFO
    assert out["missing_info"] == [{"field": "x"}]
    assert "escalation" not in out
    assert "final_answer" in out


def test_out_of_scope_never_leaves_orchestrator(graph) -> None:  # noqa: ANN001
    out = graph.invoke(
        {"query": "What is the hospital's parking policy?"},
        config={"configurable": {"thread_id": "t5"}},
    )
    assert out["scope_label"] == ScopeLabel.OUT_OF_SCOPE
    assert "final_answer" in out


def test_scope2_query_without_patient_never_reaches_patient_record(graph) -> None:  # noqa: ANN001
    # classify_scope (ARCH-025) requires has_patient for scope_2_stage/
    # scope_2_missing_info; without one, the query is out_of_scope and the
    # graph never routes into patient_record at all — defense in depth on
    # top of patient_record_agent's own no-patient-attached escalation.
    out = graph.invoke(
        {"query": "What stage of care is this patient in?"},
        config={"configurable": {"thread_id": "t6"}},
    )
    assert out["scope_label"] == ScopeLabel.OUT_OF_SCOPE
