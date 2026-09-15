"""build_citation — pure assembly of a Citation from a retrieved chunk row
(ARCH §8.1; DEVIATIONS.md #46 — pulled into Phase 2, no agent dependency)."""

from __future__ import annotations

import pytest

from app.citations.model import build_citation
from app.schemas.enums import DocumentVersionStatus

CHUNK_TEXT = "Blood cultures are recommended before antimicrobials where feasible."

CHUNK_ROW = {
    "chunk_id": "ch1",
    "text": CHUNK_TEXT,
    "char_start": 5000,
    "char_end": 5000 + len(CHUNK_TEXT),
    "page_start": 3,
    "page_end": 3,
    "section_number": "2.1.1",
    "section_path": "2 › 2.1 Investigations",
    "document_id": "doc-1",
    "document_title": "SYNTH-GL-002",
    "document_version_id": "ver-1",
    "version_label": "2024.2",
    "effective_date": "2024-06-01",
    "version_status": "active",
}


def test_builds_citation_with_correct_offsets() -> None:
    quote = "Blood cultures are recommended"
    cit = build_citation("c1", CHUNK_ROW, quote)
    assert cit.chunk_id == "ch1"
    assert cit.document_id == "doc-1"
    assert cit.version_status == DocumentVersionStatus.ACTIVE
    assert cit.quote == quote
    assert cit.quote_char_start == CHUNK_ROW["char_start"]
    assert cit.quote_char_end == CHUNK_ROW["char_start"] + len(quote)


def test_quote_not_in_chunk_raises() -> None:
    with pytest.raises(ValueError):
        build_citation("c1", CHUNK_ROW, "this text is not in the chunk")


def test_built_citation_reverifies() -> None:
    from app.citations.model import verify_citation

    quote = "recommended before antimicrobials"
    cit = build_citation("c1", CHUNK_ROW, quote)
    assert verify_citation(cit, CHUNK_TEXT)


def test_builds_citation_across_a_pdf_line_wrap_newline() -> None:
    """DEVIATIONS.md #104: a chunk with a mid-sentence line-wrap newline (a
    real PDF-extraction artifact — often with trailing spaces before the
    newline, e.g. from justified text) still builds a citation for a quote
    that reproduces the same words with normal single-space spacing."""
    wrapped_text = "Blood cultures are   \nrecommended before antimicrobials where feasible."
    row = {
        **CHUNK_ROW,
        "text": wrapped_text,
        "char_end": CHUNK_ROW["char_start"] + len(wrapped_text),
    }
    quote = "Blood cultures are recommended before antimicrobials"
    cit = build_citation("c1", row, quote)
    assert cit.quote == quote  # stores what was asked for, not the raw excerpt
    excerpt = wrapped_text[
        cit.quote_char_start - row["char_start"] : cit.quote_char_end - row["char_start"]
    ]
    # the real span is longer than the quote (3 trailing spaces + a newline
    # standing in for the quote's single space) but the words match exactly
    assert excerpt == "Blood cultures are   \nrecommended before antimicrobials"
    assert " ".join(excerpt.split()) == quote
