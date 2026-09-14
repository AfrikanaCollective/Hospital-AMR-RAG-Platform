"""Corpus / guideline version management (PRD-004, PRD-005, PRD-016; ARCH §5.1).

GET  /corpus/documents                         -> every document + its versions
GET  /corpus/documents/{id}/versions           -> one document's versions
GET  /corpus/chunks/{chunk_id}                 -> chunk text + offsets (citation
                                                   re-verification, PRD-016)
POST /corpus/versions/{id}/withdraw   (admin)  -> status=withdrawn; old citations
                                                   still resolve (ARCH §5.1)

Reads (`corpus:read`, `app.auth.rbac.ROUTE_PERMISSIONS`) are open to any
authenticated role that can reach a citation or corpus listing (clinician,
reviewer, admin) — corpus content is non-PHI reference material, not gated
per-patient. Withdrawal (`corpus:manage`) is admin-only, per ARCH §17.3
("Admins manage corpus").
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, principal_uuid, require_role
from app.db.models.corpus import Chunk, Document, DocumentVersion
from app.ingestion.corpus_access import (
    ChunkNotFoundError,
    DocumentNotFoundError,
    DocumentVersionNotFoundError,
    list_document_versions,
    list_documents,
    withdraw_version,
)
from app.ingestion.corpus_access import (
    get_chunk as get_chunk_row,
)

router = APIRouter()


def _serialize_version(v: DocumentVersion) -> dict:
    return {
        "id": str(v.id),
        "document_id": str(v.document_id),
        "version_label": v.version_label,
        "effective_date": v.effective_date.isoformat() if v.effective_date else None,
        "ingested_at": v.ingested_at.isoformat(),
        "supersedes_id": str(v.supersedes_id) if v.supersedes_id else None,
        "status": v.status,
        "content_sha256": v.content_sha256,
        "page_count": v.page_count,
        "format_profile": v.format_profile,
        "parse_quality": v.parse_quality,
    }


def _serialize_document(d: Document, versions: list[DocumentVersion]) -> dict:
    return {
        "id": str(d.id),
        "external_ref": d.external_ref,
        "title": d.title,
        "publisher": d.publisher,
        "source_uri": d.source_uri,
        "classification": d.classification,
        "licence": d.licence,
        "versions": [_serialize_version(v) for v in versions],
    }


def _serialize_chunk(c: Chunk) -> dict:
    return {
        "id": str(c.id),
        "document_version_id": str(c.document_version_id),
        "section_path": c.section_path,
        "section_number": c.section_number,
        "heading": c.heading,
        "page_start": c.page_start,
        "page_end": c.page_end,
        "char_start": c.char_start,
        "char_end": c.char_end,
        "ordinal": c.ordinal,
        "chunk_type": c.chunk_type,
        "text": c.text,
        "meta": c.meta,
    }


@router.get("/documents")
async def list_documents_route(
    _principal: Principal = Depends(require_role("clinician", "reviewer", "admin")),
    session: Session = Depends(get_db),
) -> list[dict]:
    documents = list_documents(session)
    return [_serialize_document(d, list_document_versions(session, d.id)) for d in documents]


@router.get("/documents/{document_id}/versions")
async def list_versions_route(
    document_id: str,
    _principal: Principal = Depends(require_role("clinician", "reviewer", "admin")),
    session: Session = Depends(get_db),
) -> list[dict]:
    try:
        versions = list_document_versions(session, uuid.UUID(document_id))
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [_serialize_version(v) for v in versions]


@router.get("/chunks/{chunk_id}")
async def get_chunk_route(
    chunk_id: str,
    _principal: Principal = Depends(require_role("clinician", "reviewer", "admin")),
    session: Session = Depends(get_db),
) -> dict:
    try:
        chunk = get_chunk_row(session, uuid.UUID(chunk_id))
    except ChunkNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _serialize_chunk(chunk)


@router.post("/versions/{version_id}/withdraw")
async def withdraw_version_route(
    version_id: str,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_db),
) -> dict:
    try:
        version = withdraw_version(
            session,
            uuid.UUID(version_id),
            actor_id=principal_uuid(principal),
            actor_role="admin",
        )
    except DocumentVersionNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _serialize_version(version)
