"""Escalation agent (ARCH §10.2, §12).

Does: package an escalation — reason code, trigger detail, candidate answer,
retrieved evidence, patient-context handle; create the hitl.escalation row;
enqueue for review; notify reviewers.
Does NOT: answer the clinical question; alter the candidate.
Access: hitl schema (write), memory.conversation (read).
Tools: create_escalation, enqueue_review, notify_reviewers.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (ARCH §12)")
