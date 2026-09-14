"""Grounding gate (ARCH §8.3, ARCH-015)."""

from __future__ import annotations

from app.grounding.verifier import citations_for_segments, lexical_overlap, verify
from app.schemas.enums import GroundingVerdict


def _chunk(chunk_id: str, text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "document_id": "doc1",
        "document_title": "Newborn Care Guideline",
        "document_version_id": "v1",
        "version_label": "2021",
        "version_status": "active",
        "effective_date": None,
        "section_number": "3.2",
        "section_path": "Assessment > Vitals",
        "page_start": 5,
        "page_end": 5,
        "char_start": 100,
        "char_end": 200,
    }


SNAPSHOT = [_chunk("ch1", "Record respiratory rate at presentation for every neonate.")]


def test_all_supported_releases() -> None:
    segments = [
        {"type": "framing", "text": "Per the retrieved guideline:"},
        {
            "type": "claim",
            "text": "record respiratory rate at presentation",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        },
    ]
    report = verify(segments, SNAPSHOT)
    assert report.action == "release"
    assert all(v.verdict == GroundingVerdict.SUPPORTED for v in report.per_segment)


def test_unresolved_citation_id_escalate_or_strip() -> None:
    segments = [
        {"type": "claim", "text": "x", "citation_ids": ["c99"], "quote": "anything"},
    ]
    report = verify(segments, SNAPSHOT)
    assert report.per_segment[0].verdict == GroundingVerdict.UNSUPPORTED
    assert report.per_segment[0].reason == "citation_not_retrieved"
    assert report.action == "escalate"  # only claim segment, nothing left to keep


def test_quote_not_verbatim_in_chunk() -> None:
    segments = [
        {
            "type": "claim",
            "text": "some claim",
            "citation_ids": ["c1"],
            "quote": "this text is not in the chunk",
        }
    ]
    report = verify(segments, SNAPSHOT)
    assert report.per_segment[0].reason == "quote_mismatch"


def test_directive_phrasing_is_scope_violation_and_forces_escalate() -> None:
    segments = [
        {
            "type": "claim",
            "text": "You should start the patient on antibiotics now.",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        },
        {
            "type": "claim",
            "text": "record respiratory rate at presentation",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        },
    ]
    report = verify(segments, SNAPSHOT)
    assert report.action == "escalate"
    assert report.per_segment[0].reason == "scope_violation"


def test_partial_strip_keeps_supported_claims() -> None:
    segments = [
        {
            "type": "claim",
            "text": "record respiratory rate at presentation",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        },
        {"type": "claim", "text": "unsupported claim", "citation_ids": ["c99"], "quote": "nope"},
    ]
    report = verify(segments, SNAPSHOT)
    assert report.action == "partial_strip"
    assert report.stripped_segment_indexes == [1]


def test_weak_entailment_releases_marked() -> None:
    segments = [
        {
            "type": "claim",
            "text": "presentation matters for neonates broadly speaking overall",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        }
    ]
    report = verify(segments, SNAPSHOT, entailment_fn=lambda claim, quote: "partly")  # noqa: ARG005
    assert report.action == "release_marked"
    assert report.per_segment[0].verdict == GroundingVerdict.WEAK


def test_model_entailment_no_marks_unsupported() -> None:
    # Deliberately mid-range lexical overlap so the hybrid strategy defers to
    # entailment_fn instead of trusting a confident lexical read.
    segments = [
        {
            "type": "claim",
            "text": "record respiratory rate every newborn admitted unit",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        }
    ]
    report = verify(
        segments,
        SNAPSHOT,
        entailment_fn=lambda claim, quote: "no",  # noqa: ARG005
    )
    assert report.per_segment[0].reason == "not_entailed"


def test_lexical_overlap_bounds() -> None:
    assert lexical_overlap("", "anything") == 0.0
    assert (
        lexical_overlap("respiratory rate presentation", "Record respiratory rate at presentation")
        == 1.0
    )


def test_citations_for_segments_builds_citation_objects() -> None:
    segments = [
        {
            "type": "claim",
            "text": "record respiratory rate at presentation",
            "citation_ids": ["c1"],
            "quote": "Record respiratory rate at presentation",
        }
    ]
    citations = citations_for_segments(segments, SNAPSHOT)
    assert set(citations) == {"c1"}
    assert citations["c1"].chunk_id == "ch1"
    assert citations["c1"].quote == "Record respiratory rate at presentation"
