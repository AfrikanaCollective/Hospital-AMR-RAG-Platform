"""Request/response schemas for `/ingest/*` (ARCH §5, ARCH-038, ARCH-039).

Record ingestion request bodies use `app.schemas.record.RecordIngestBatch`
directly (already defined in Phase 1) rather than a new schema here.
"""

from __future__ import annotations

from pydantic import BaseModel


class DocumentIngestResponse(BaseModel):
    document_id: str
    document_version_id: str
    version_status: str  # active | superseded | withdrawn
    created: bool  # False => idempotent no-op (identical content_sha256 already ingested)
    processing_enqueued: bool  # True => app.ingestion.tasks.process_document was enqueued


class RecordIngestResponse(BaseModel):
    patient_record_ids: list[str]
    data_class: str
    count: int
