"""Retrieval confidence assessment (ARCH §7.5; PRD-013, PRD-C4).

Low confidence => NO general-knowledge answer: return "no guideline found"
(if essentially nothing retrieved) or escalate (trigger_code = low_confidence).
Thresholds are config (RETRIEVAL_MIN_SCORE, SUPPORT_SCORE_FLOOR,
MIN_SUPPORTING_CHUNKS) and are pinned in eval snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class ConfidenceVerdict:
    top_score: float
    supporting_count: int
    low_confidence: bool
    essentially_empty: bool


def assess(scores: list[float]) -> ConfidenceVerdict:
    s = get_settings()
    top = max(scores) if scores else 0.0
    supporting = sum(1 for x in scores if x >= s.support_score_floor)
    essentially_empty = top < s.support_score_floor or not scores
    low = essentially_empty or top < s.retrieval_min_score or supporting < s.min_supporting_chunks
    return ConfidenceVerdict(top, supporting, low, essentially_empty)
