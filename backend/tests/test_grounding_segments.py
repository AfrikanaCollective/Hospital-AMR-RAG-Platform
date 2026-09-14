"""Answer segmentation parsing (ARCH §8.2)."""

from __future__ import annotations

import json

import pytest

from app.grounding.segments import SegmentParseError, is_structurally_valid, parse_segments
from app.schemas.enums import SegmentType


def test_parses_claim_and_framing_segments() -> None:
    raw = json.dumps(
        [
            {"type": "framing", "text": "Per the retrieved guideline:"},
            {
                "type": "claim",
                "text": "Guideline X recommends recording respiratory rate at presentation.",
                "citation_ids": ["c1"],
                "quote": "record respiratory rate at presentation",
            },
        ]
    )
    segments = parse_segments(raw)
    assert segments[0]["type"] == SegmentType.FRAMING
    assert segments[1]["type"] == SegmentType.CLAIM
    assert segments[1]["citation_ids"] == ["c1"]
    assert is_structurally_valid(segments)


def test_accepts_a_pre_parsed_list() -> None:
    raw = [{"type": "framing", "text": "no guideline found"}]
    segments = parse_segments(raw)
    assert segments[0]["type"] == SegmentType.FRAMING


@pytest.mark.parametrize("raw", ["not json", "{}", json.dumps([{"text": "missing type"}])])
def test_malformed_output_raises(raw: str) -> None:
    with pytest.raises(SegmentParseError):
        parse_segments(raw)


def test_unknown_segment_type_raises() -> None:
    with pytest.raises(SegmentParseError):
        parse_segments(json.dumps([{"type": "opinion", "text": "x"}]))


def test_structurally_invalid_claim_missing_citation() -> None:
    segments = parse_segments(
        json.dumps([{"type": "claim", "text": "x", "citation_ids": [], "quote": "x"}])
    )
    assert not is_structurally_valid(segments)


def test_empty_segment_list_is_invalid() -> None:
    assert not is_structurally_valid([])
