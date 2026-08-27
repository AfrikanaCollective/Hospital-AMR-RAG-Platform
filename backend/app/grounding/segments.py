"""Answer segmentation (ARCH §8.2).

The synthesis agent must emit an ordered list of segments: claim (>=1 citation
+ verbatim quote) or framing (non-claim connective text, constrained by the
wording filter). Free-form prose without this structure is rejected and
regenerated once; a second failure escalates.
"""

from __future__ import annotations

from app.schemas.enums import SegmentType


def parse_segments(raw: object) -> list[dict]:
    """Validate the model's segmented output. Phase 3."""
    raise NotImplementedError("Phase 3 (ARCH §8.2)")


def is_structurally_valid(segments: list[dict]) -> bool:
    for seg in segments:
        if seg.get("type") == SegmentType.CLAIM and not seg.get("citation_ids"):
            return False
        if seg.get("type") == SegmentType.CLAIM and not seg.get("quote"):
            return False
    return bool(segments)
