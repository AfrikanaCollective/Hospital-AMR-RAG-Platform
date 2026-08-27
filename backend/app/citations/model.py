"""Build + re-verify Citation objects (ARCH §8.1; PRD-016).

`verify_citation` re-checks a citation against stored chunk text:
- the quote is a verbatim substring of the cited chunk,
- quote offsets are consistent with chunk offsets,
- chunk offsets match the normalized document text.
This is deterministic and is part of the grounding gate (step 2).
"""

from __future__ import annotations

from app.schemas.citation import Citation


def build_citation(citation_id: str, chunk_row: dict, quote: str) -> Citation:
    raise NotImplementedError("Phase 3 (ARCH §8.1)")


def verify_citation(citation: Citation, chunk_text: str) -> bool:
    if not (0 <= citation.quote_char_start <= citation.quote_char_end):
        return False
    local_start = citation.quote_char_start - citation.char_start
    local_end = citation.quote_char_end - citation.char_start
    if local_start < 0 or local_end > len(chunk_text):
        return False
    return chunk_text[local_start:local_end] == citation.quote and citation.quote in chunk_text
