"""Corpus / guideline version management (PRD-004, PRD-005; ARCH §5.1).

GET  /corpus/documents
GET  /corpus/documents/{id}/versions
POST /corpus/versions/{id}/withdraw   (admin)  -> status=withdrawn; old citations still resolve
GET  /corpus/chunks/{chunk_id}                 -> chunk text + offsets (citation re-verification,
                                                   PRD-016)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/documents", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_documents() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: corpus management (ARCH §5.1).")


@router.get("/chunks/{chunk_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_chunk(chunk_id: str) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: chunk retrieval (ARCH-014).")
