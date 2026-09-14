"""Answer segmentation (ARCH §8.2).

The synthesis agent must emit an ordered list of segments: claim (>=1 citation
+ verbatim quote) or framing (non-claim connective text, constrained by the
wording filter). Free-form prose without this structure is rejected and
regenerated once; a second failure escalates.
"""

from __future__ import annotations

import json

from app.schemas.enums import SegmentType


class SegmentParseError(ValueError):
    """The model's output is not valid JSON, or not a list of segments."""


def parse_segments(raw: object) -> list[dict]:
    """Parse + normalize the synthesis model's segmented output (the
    `guideline_synthesis.md` "Output format" contract): a JSON list of
    `{"type": "claim", "text", "citation_ids", "quote"}` or
    `{"type": "framing", "text"}` objects.

    Raises `SegmentParseError` on malformed JSON or a non-list payload.
    Structural validity (claim segments carrying citations/a quote, the list
    being non-empty) is checked separately by `is_structurally_valid` — the
    caller (guideline_synthesis agent) treats that as "reject and regenerate
    once, then escalate" (ARCH §8.2), distinct from a hard parse failure.
    """
    text = raw if isinstance(raw, str) else json.dumps(raw)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SegmentParseError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SegmentParseError("model output must be a JSON list of segments")

    segments: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or "type" not in item or "text" not in item:
            raise SegmentParseError(f"malformed segment (needs type + text): {item!r}")
        seg_type = item["type"]
        if seg_type not in (SegmentType.CLAIM, SegmentType.FRAMING):
            raise SegmentParseError(f"unknown segment type: {seg_type!r}")
        segment: dict = {"type": SegmentType(seg_type), "text": str(item["text"])}
        if seg_type == SegmentType.CLAIM:
            segment["citation_ids"] = [str(c) for c in item.get("citation_ids") or []]
            segment["quote"] = str(item.get("quote") or "")
        segments.append(segment)
    return segments


def is_structurally_valid(segments: list[dict]) -> bool:
    for seg in segments:
        if seg.get("type") == SegmentType.CLAIM and not seg.get("citation_ids"):
            return False
        if seg.get("type") == SegmentType.CLAIM and not seg.get("quote"):
            return False
    return bool(segments)
