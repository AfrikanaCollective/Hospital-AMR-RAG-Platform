"""Structure-aware PDF parsing (ARCH §5.1, ARCH-013).

Produces: one normalized document text with a stable character index, a section
tree (heading detection from numbering / font size / regex on `^\\d+(\\.\\d+)*\\s`),
and a per-document parse-quality score. Low-quality parses get a visible badge
and admin review (self-critique §21a mitigation).

Phase 2 implements (primary: a layout-aware parser; fallback: plain text
extraction with a logged quality warning).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedDocument:
    normalized_text: str
    sections: list[dict]  # [{number, heading, path, char_start, char_end, page_start, page_end}]
    page_count: int
    parse_quality: float  # 0..1


def parse_pdf(path: str) -> ParsedDocument:
    raise NotImplementedError("Phase 2 (ARCH §5.1)")
