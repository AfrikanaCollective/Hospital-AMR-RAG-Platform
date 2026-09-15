"""Citation re-verification against stored chunk text (ARCH §8.1; PRD-016)."""

from __future__ import annotations

from app.citations.model import verify_citation
from app.schemas.citation import Citation

CHUNK_TEXT = (
    "The guideline recommends recording respiratory rate and oxygen saturation at presentation."
)


def _cit(quote: str, qs: int, qe: int) -> Citation:
    return Citation(
        citation_id="c1",
        document_id="d1",
        document_title="SYNTH-GL-001",
        document_version_id="v1",
        version_label="2025.1",
        chunk_id="ch1",
        page_start=2,
        page_end=2,
        char_start=1000,
        char_end=1000 + len(CHUNK_TEXT),
        quote=quote,
        quote_char_start=1000 + qs,
        quote_char_end=1000 + qe,
    )


def test_valid_quote_verifies() -> None:
    q = "recording respiratory rate and oxygen saturation"
    s = CHUNK_TEXT.index(q)
    assert verify_citation(_cit(q, s, s + len(q)), CHUNK_TEXT)


def test_altered_quote_fails() -> None:
    q = "recording heart rate and oxygen saturation"  # not in the chunk
    assert not verify_citation(_cit(q, 14, 14 + len(q)), CHUNK_TEXT)


def test_offset_out_of_range_fails() -> None:
    q = "respiratory rate"
    assert not verify_citation(_cit(q, 5000, 5016), CHUNK_TEXT)


def test_verifies_across_a_pdf_line_wrap_newline() -> None:
    """DEVIATIONS.md #104: quote_char_start/end may point at a raw span one
    or more characters longer than the stored quote (a line-wrap newline
    standing in for a space) — verify_citation must still pass."""
    wrapped = "The guideline recommends recording respiratory\nrate and oxygen saturation."
    q = "The guideline recommends recording respiratory rate"
    cit = _cit(q, 0, len(q) + 1)  # +1: the newline in the source, not counted in q
    assert verify_citation(cit, wrapped)
