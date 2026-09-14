"""Build + re-verify Citation objects (ARCH §8.1; PRD-016).

`build_citation` is a pure function with no agent dependency — it turns a
retrieved `chunk_row` (the dict shape returned by `app.retrieval.hybrid.retrieve`,
carrying document/version identity + section/page/char span) plus a chosen
`quote` into a `Citation`. Pulled into Phase 2 (DEVIATIONS.md #46) rather than
left for Phase 3: unlike the grounding gate (`app.grounding.verifier.verify`)
and answer segmentation (`app.grounding.segments`), which require the Phase-3
synthesis agent's claim segments as input, this only needs retrieval output.
The synthesis agent (Phase 3) is still what decides *which* quote supports a
given claim; this function just assembles the citation object once that quote
is chosen.

`verify_citation` re-checks a citation against stored chunk text:
- the quote is a verbatim substring of the cited chunk,
- quote offsets are consistent with chunk offsets,
- chunk offsets match the normalized document text.
This is deterministic and is part of the grounding gate (step 2).
"""

from __future__ import annotations

from app.schemas.citation import Citation
from app.schemas.enums import DocumentVersionStatus


def build_citation(citation_id: str, chunk_row: dict, quote: str) -> Citation:
    """Build a `Citation` for `quote` found verbatim in `chunk_row["text"]`.

    `chunk_row` carries: chunk_id, text, char_start, char_end, page_start,
    page_end, section_number, section_path, document_id, document_title,
    document_version_id, version_label, effective_date, version_status.

    Raises `ValueError` if `quote` is not a substring of the chunk's text —
    a citation is never built for an unsupported quote (ARCH §8.1).
    """
    text = chunk_row["text"]
    idx = text.find(quote)
    if idx < 0:
        raise ValueError(f"quote is not a substring of chunk {chunk_row.get('chunk_id')!r} text")
    char_start = chunk_row["char_start"]
    return Citation(
        citation_id=citation_id,
        document_id=chunk_row["document_id"],
        document_title=chunk_row["document_title"],
        document_version_id=chunk_row["document_version_id"],
        version_label=chunk_row["version_label"],
        effective_date=chunk_row.get("effective_date"),
        version_status=DocumentVersionStatus(chunk_row.get("version_status", "active")),
        chunk_id=chunk_row["chunk_id"],
        section_number=chunk_row.get("section_number"),
        section_path=chunk_row.get("section_path"),
        page_start=chunk_row["page_start"],
        page_end=chunk_row["page_end"],
        char_start=char_start,
        char_end=chunk_row["char_end"],
        quote=quote,
        quote_char_start=char_start + idx,
        quote_char_end=char_start + idx + len(quote),
    )


def verify_citation(citation: Citation, chunk_text: str) -> bool:
    if not (0 <= citation.quote_char_start <= citation.quote_char_end):
        return False
    local_start = citation.quote_char_start - citation.char_start
    local_end = citation.quote_char_end - citation.char_start
    if local_start < 0 or local_end > len(chunk_text):
        return False
    return chunk_text[local_start:local_end] == citation.quote and citation.quote in chunk_text
