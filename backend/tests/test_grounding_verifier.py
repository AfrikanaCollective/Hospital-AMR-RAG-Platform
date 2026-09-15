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


def test_quote_tolerates_pdf_line_wrap_newline() -> None:
    """DEVIATIONS.md #104: real PDF-extracted chunk text routinely has a
    line-wrap newline mid-sentence (a layout artifact, not a semantic break);
    a model naturally normalizes it to a single space when reproducing a
    quote. This must still verify and get a real citation — reproduces the
    exact real-world failure found end-to-end against a live model."""
    wrapped_snapshot = [
        _chunk(
            "ch1",
            "Newly born babies who do not breathe spontaneously after thorough drying should be\n"
            "stimulated by rubbing the back 2-3 times before initiating ventilation.",
        )
    ]
    quote = (
        "Newly born babies who do not breathe spontaneously after thorough drying "
        "should be stimulated by rubbing the back 2-3 times before initiating ventilation."
    )
    segments = [
        # text mirrors the quote closely (matching this file's existing
        # SUPPORTED-verdict test pattern) so lexical entailment reads high
        # confidence — isolates what's under test (quote matching), not
        # entailment scoring, which has its own dedicated tests below.
        {
            "type": "claim",
            "text": (
                "newly born babies who do not breathe spontaneously after thorough drying "
                "should be stimulated by rubbing the back"
            ),
            "citation_ids": ["c1"],
            "quote": quote,
        }
    ]
    report = verify(segments, wrapped_snapshot)
    assert report.per_segment[0].verdict == GroundingVerdict.SUPPORTED
    assert report.action == "release"

    citations = citations_for_segments(segments, wrapped_snapshot)
    assert "c1" in citations
    cit = citations["c1"]
    # Offsets must point at the ACTUAL match in the source text (newline and
    # all), not just len(quote) from wherever the first word was found — the
    # excerpt they bound must normalize back to exactly the quote.
    chunk_text = wrapped_snapshot[0]["text"]
    excerpt = chunk_text[
        cit.quote_char_start - wrapped_snapshot[0]["char_start"] : cit.quote_char_end
        - wrapped_snapshot[0]["char_start"]
    ]
    assert "\n" in excerpt
    assert " ".join(excerpt.split()) == quote


def test_quote_does_not_tolerate_reworded_text() -> None:
    """The whitespace tolerance must not become a fuzzy-match: a genuinely
    different word must still fail, even with only a small change."""
    segments = [
        {
            "type": "claim",
            "text": "some claim",
            "citation_ids": ["c1"],
            "quote": "Record heart rate at presentation",  # "heart" not "respiratory"
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


def test_over_cited_segment_verified_citation_ids_is_only_the_matching_subset() -> None:
    """DEVIATIONS.md #107: a claim citing two ids where only one chunk
    actually contains the quote is SUPPORTED (any match is enough) — but
    `verified_citation_ids` on the verdict must name only the id(s) that
    actually verify, so a caller can narrow the segment before returning it
    rather than leaving a dangling, uncited reference in the answer."""
    two_source_snapshot = SNAPSHOT + [_chunk("ch2", "Start antibiotics within one hour.")]
    segments = [
        {
            "type": "claim",
            "text": "record respiratory rate at presentation",
            "citation_ids": ["c1", "c2"],  # c2's chunk does not contain the quote
            "quote": "Record respiratory rate at presentation",
        }
    ]
    report = verify(segments, two_source_snapshot)
    assert report.action == "release"
    assert report.per_segment[0].verified_citation_ids == ["c1"]
