"""Structure-aware, recommendation-atomic chunking (ARCH §6, ARCH-013; PRD-004).

Rules (priority order):
1. Never split an atomic recommendation + its qualifiers (soft cap 1024 tokens;
   if exceeded, split on sentence boundaries but tag `split_group_id`).
2. Chunk within the deepest heading; target 350-600 tokens, ~15% prose overlap
   (overlap carries no citation authority).
3. Tables -> one `table` chunk (Markdown-serialized, caption + heading prepended).
4. Criteria lists -> `criteria` chunks with structured meta.criteria[]
   (field, operator, value, unit) where extractable.
5. Embed text is prefixed with section_path; citation view shows the raw slice.
6. Each chunk references a parent_chunk_id for `expand_context`.

Phase 2 implements. Every chunk retains document/version/section/page/char span.
"""

from __future__ import annotations

from app.ingestion.pdf_parse import ParsedDocument


def chunk_document(doc: ParsedDocument) -> list[dict]:
    raise NotImplementedError("Phase 2 (ARCH §6)")
