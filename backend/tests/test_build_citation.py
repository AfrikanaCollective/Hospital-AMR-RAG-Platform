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
