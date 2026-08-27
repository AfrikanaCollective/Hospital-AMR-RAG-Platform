"""Ingestion endpoints (PRD-001, PRD-002, PRD-003, PRD-006; ARCH §5).

POST /ingest/documents        (admin)   -> upload a guideline PDF; enqueue parse/chunk/embed
POST /ingest/records/file     (admin)   -> upload CSV/JSON patient records
POST /ingest/records          (service) -> one record (or bounded batch) via API
Record ingestion validates against app.schemas.record and rejects batches that
fail the real-data heuristic (DEVIATIONS.md #16, #21).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role

router = APIRouter()


@router.post("/documents", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("admin"))])
async def ingest_document() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: PDF ingestion (ARCH §5.1).")


@router.post("/records/file", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("admin", "service"))])
async def ingest_records_file() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: record ingestion (ARCH §5.2).")


@router.post("/records", status_code=status.HTTP_501_NOT_IMPLEMENTED,
             dependencies=[Depends(require_role("service"))])
async def ingest_records_api() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: record ingestion (ARCH §5.2).")
