"""Grounding gate (ARCH §8.3, ARCH-015).

Per claim segment: (1) citation resolves to a chunk in THIS turn's snapshot,
(2) quote is a verbatim substring of that chunk + offsets check, (3) entailment
(lexical overlap + one constrained model call), (4) scope/wording
(app.grounding.wording).

Verdict policy (ARCH §8.3):
  all supported            -> release (+ disclaimer)
  only weak                -> release marked + queue for review
  unsupported, strip ok    -> partial-strip, re-check, release reduced + log stripped
  unsupported, strip bad / directive scope_violation -> ESCALATE, hold
  low-confidence/empty      -> never reaches here with claims
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.enums import GroundingVerdict


@dataclass
class SegmentVerdict:
    segment_index: int
    verdict: GroundingVerdict
    reason: str | None = None  # citation_not_retrieved | quote_mismatch | not_entailed | scope_violation


@dataclass
class GroundingReport:
    per_segment: list[SegmentVerdict]
    action: str  # release | release_marked | partial_strip | escalate
    stripped_segment_indexes: list[int]


def verify(segments: list[dict], retrieval_snapshot: list[dict]) -> GroundingReport:
    raise NotImplementedError("Phase 3 (ARCH-015, ARCH §8.3)")
