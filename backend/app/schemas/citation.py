"""Citation object (ARCH-014; PRD-011, PRD-016).

Minimum per constraint #4: document ID + version + section/page + chunk offset.
The `quote` + its offsets are what the grounding check (ARCH-015) and the UI
highlight use, and what makes a citation re-verifiable against stored chunk text.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.enums import DocumentVersionStatus


class Citation(BaseModel):
    citation_id: str = Field(description="stable id within one answer, e.g. 'c1'")

    # document identity + version (minimum)
    document_id: str
    document_title: str
    document_version_id: str
    version_label: str
    effective_date: date | None = None
    version_status: DocumentVersionStatus = DocumentVersionStatus.ACTIVE

    # locus (minimum: section/page)
    chunk_id: str
    section_number: str | None = None
    section_path: str | None = None
    page_start: int
    page_end: int

    # chunk offset (minimum: chunk offset)
    char_start: int = Field(ge=0, description="offset within the normalized document text")
    char_end: int = Field(ge=0)

    # verbatim supporting span — substring of the cited chunk's stored text
    quote: str
    quote_char_start: int = Field(ge=0)
    quote_char_end: int = Field(ge=0)
