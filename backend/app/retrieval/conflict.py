"""Conflict detection between retrieved sources (ARCH §7.6; PRD-014).

Flags material disagreement: (a) same section_number/topic across two `active`
versions with different recommendation text, or (b) a lightweight
NLI/contradiction pass between top recommendation chunks. Any flag =>
escalation (conflicting_sources); both sides are surfaced with citations, never
auto-resolved. Starts conservative (over-flag), tuned on the eval set
(self-critique §21a).
"""

from __future__ import annotations

from app.agents.state import RetrievalItem


def detect_conflicts(items: list[RetrievalItem]) -> list[dict]:
    raise NotImplementedError("Phase 2 (ARCH §7.6)")
