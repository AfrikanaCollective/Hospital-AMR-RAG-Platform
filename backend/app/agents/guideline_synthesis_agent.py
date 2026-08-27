"""Guideline-synthesis agent (SCOPE-1; ARCH §10.2, §8.2, §9.1).

Does: turn (question + retrieved chunks [+ stage label] [+ missing-info]) into
SEGMENTED output — claim segments each with citation_ids and a verbatim quote;
framing segments non-directive. Emits `no_guideline` if the retrieved set can't
support an answer.
Does NOT: see raw PHI (only an orchestrator-built feature summary); use
knowledge outside the retrieved chunks; produce directive text ("you should…").
Access: ONLY the chunk texts passed in + the question. No store access.
Tools: get_chunk (restricted to this turn's set), get_citation_metadata.

Prompt template: app/agents/prompts/guideline_synthesis.md — enforces the
"Guideline X recommends…" framing (SCOPE-1.2). The §8.3 wording check is a
second line of defense.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (SCOPE-1, ARCH §8.2, ARCH-037)")
