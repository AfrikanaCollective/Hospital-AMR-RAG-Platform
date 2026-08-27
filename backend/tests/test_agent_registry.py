"""Per-agent tool allow-list enforcement (ARCH §10, ARCH-034)."""

from __future__ import annotations

import pytest

from app.agents.registry import AGENT_TOOLS, call_tool, register_tool


def test_synthesis_agent_has_no_store_or_retrieval_tools() -> None:
    tools = AGENT_TOOLS["guideline_synthesis"]
    assert tools == frozenset({"get_chunk", "get_citation_metadata"})
    assert "hybrid_search" not in tools
    assert "get_patient_fields" not in tools


def test_only_patient_record_agent_can_get_patient_fields() -> None:
    can = {a for a, t in AGENT_TOOLS.items() if "get_patient_fields" in t}
    assert can == {"patient_record", "missing_info"}
    assert "guideline_synthesis" not in can
    assert "retrieval" not in can


def test_stub_agents_have_no_tools() -> None:
    assert AGENT_TOOLS["local_adaptation"] == frozenset()
    assert AGENT_TOOLS["next_step_recommender"] == frozenset()


def test_call_tool_rejects_out_of_allowlist() -> None:
    register_tool("get_chunk", lambda cid: {"id": cid})
    assert call_tool("guideline_synthesis", "get_chunk", "ch1") == {"id": "ch1"}
    with pytest.raises(PermissionError):
        call_tool("guideline_synthesis", "hybrid_search", "q")
