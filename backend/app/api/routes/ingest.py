"""Ingestion endpoints (PRD-001, PRD-002, PRD-003, PRD-006; ARCH §5, ARCH-039).

POST /ingest/documents        (admin)          -> upload a guideline PDF; enqueue parse/chunk/embed
POST /ingest/records/file     (admin/service)  -> upload CSV/JSON patient records (wide,
                                                   one row/patient)
POST /ingest/records/eav      (admin/service)  -> upload an EAV/long CSV + a mapping ref (ARCH-039)
POST /ingest/records          (service)        -> one record (or bounded batch) via API

Record ingestion validates against app.schemas.record and applies the
data-class guard: `synthetic` (marker) or attested `deidentified`, else reject
(DEVIATIONS.md #16, #21, #33).

File storage / mapping-spec resolution (DEVIATIONS.md #65):
- an uploaded guideline document is written into `SAMPLE_GUIDELINES_DIR`
  (the same directory an operator manually drops PDFs into — ARCH-038); a
  same-name file already there with *different* content is a 409, never
  silently overwritten.
- `/ingest/records/eav`'s `mapping_ref` names a directory under
  `PATIENT_RECORDS_DIR/deidentified/<mapping_ref>/field_mapping.yaml` — the
  same convention `scripts/ingest_deidentified_records.py` and the bundled
  `newborn_nbu_2021` dataset already use; this route is the HTTP path to the
  same `FileEavSource` + `ingest_records` pipeline that script drives from
  the CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.config import get_settings
from app.ingestion.documents import DocumentMetadata, create_or_supersede_document_version
from app.ingestion.records import (
    DatasetAttestation,
    MissingAttestationError,
    RealDataSuspectedError,
    ingest_records,
    parse_wide_upload,
    resolve_data_class,
)
from app.ingestion.sources import FileEavSource
from app.ingestion.tasks import process_document
from app.schemas.ingest import DocumentIngestResponse, RecordIngestResponse
from app.schemas.record import RecordIngestBatch

router = APIRouter()

# ARCH §5.2 "one record (or bounded batch) via API" — a deliberate bound, not
# a general pagination limit; a larger push belongs on the file/EAV paths.
_MAX_API_BATCH_RECORDS = 500


def _store_uploaded_document(content: bytes, filename: str, content_sha256: str) -> Path:
    target_dir = Path(get_settings().sample_guidelines_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    if target_path.exists():
        existing_sha256 = hashlib.sha256(target_path.read_bytes()).hexdigest()
        if existing_sha256 != content_sha256:
            raise FileExistsError(
                f"{filename!r} already exists in {target_dir} with different content — "
                "rename the upload or remove the conflicting file first"
            )
        return target_path  # identical content already on disk; not an error
    target_path.write_bytes(content)
    return target_path


def _attestation_from_json(attestation_json: str | None) -> DatasetAttestation | None:
    if not attestation_json:
        return None
    try:
        values = json.loads(attestation_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"attestation_json is not valid JSON: {exc}"
        ) from exc
    if not isinstance(values, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "attestation_json must be a JSON object")
    return DatasetAttestation(values=values)


def _guarded_ingest(
    session: Session,
    records: list,
    *,
    declared_provenance: str | None,
    dataset_id: str | None,
    attestation: DatasetAttestation | None,
    source: str,
) -> RecordIngestResponse:
    try:
        ids = ingest_records(
            session,
            records,
            declared_provenance=declared_provenance,
            dataset_id=dataset_id,
            attestation=attestation,
            source=source,
        )
    except (MissingAttestationError, RealDataSuspectedError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return RecordIngestResponse(
        patient_record_ids=[str(i) for i in ids],
        data_class=str(resolve_data_class(declared_provenance)),
        count=len(ids),
    )


@router.post(
    "/documents",
    response_model=DocumentIngestResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def ingest_document(  # noqa: PLR0917 - FastAPI Form/Depends params, never called positionally
    file: UploadFile,
    title: Annotated[str, Form()],
    version_label: Annotated[str, Form()],
    publisher: Annotated[str | None, Form()] = None,
    external_ref: Annotated[str | None, Form()] = None,
    licence: Annotated[str | None, Form()] = None,
    effective_date: Annotated[date | None, Form()] = None,
    format_profile: Annotated[str | None, Form()] = None,
    topic_tags: Annotated[list[str], Form()] = [],  # noqa: B006 - FastAPI Form default, not mutated
    session: Session = Depends(get_db),
) -> DocumentIngestResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file upload")
    filename = file.filename or "upload"
    if Path(filename).suffix.lower() not in (".pdf", ".md", ".markdown", ".txt"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"unsupported guideline file type: {filename!r}"
        )
    content_sha256 = hashlib.sha256(content).hexdigest()
    try:
        stored_path = _store_uploaded_document(content, filename, content_sha256)
    except FileExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    meta = DocumentMetadata(
        title=title,
        publisher=publisher,
        external_ref=external_ref,
        source_uri=str(stored_path),
        licence=licence,
        version_label=version_label,
        effective_date=effective_date,
        topic_tags=list(topic_tags),
        format_profile=format_profile,
    )
    version, created = create_or_supersede_document_version(
        session, meta, content_sha256=content_sha256
    )
    if created:
        process_document.delay(str(version.id), topic_tags=list(topic_tags))
    return DocumentIngestResponse(
        document_id=str(version.document_id),
        document_version_id=str(version.id),
        version_status=version.status,
        created=created,
        processing_enqueued=created,
    )


@router.post(
    "/records/file",
    response_model=RecordIngestResponse,
    dependencies=[Depends(require_role("admin", "service"))],
)
async def ingest_records_file(
    file: UploadFile,
    declared_provenance: Annotated[str, Form()],
    dataset_id: Annotated[str | None, Form()] = None,
    attestation_json: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_db),
) -> RecordIngestResponse:
    content = await file.read()
    try:
        records = parse_wide_upload(content, file.filename or "upload")
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    attestation = _attestation_from_json(attestation_json)
    return _guarded_ingest(
        session,
        records,
        declared_provenance=declared_provenance,
        dataset_id=dataset_id,
        attestation=attestation,
        source="file",
    )


@router.post(
    "/records/eav",
    response_model=RecordIngestResponse,
    dependencies=[Depends(require_role("admin", "service"))],
)
async def ingest_records_eav(
    file: UploadFile,
    mapping_ref: Annotated[str, Form()],
    dataset_id: Annotated[str | None, Form()] = None,
    attestation_json: Annotated[str | None, Form()] = None,
    session: Session = Depends(get_db),
) -> RecordIngestResponse:
    """EAV/long CSV + `mapping_ref` (a directory under
    `PATIENT_RECORDS_DIR/deidentified/`, per `field_mapping.yaml`'s own
    convention). Pivots long->wide, applies the mapping spec, validates,
    persists — the same pipeline `scripts/ingest_deidentified_records.py`
    drives from the CLI (ARCH-039)."""
    mapping_path = (
        Path(get_settings().patient_records_dir)
        / "deidentified"
        / mapping_ref
        / "field_mapping.yaml"
    )
    if not mapping_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no field_mapping.yaml for mapping_ref={mapping_ref!r}"
        )

    content = await file.read()
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(content)
        src = FileEavSource(tmp_path, mapping_path)
        desc = src.describe()
        try:
            records = list(src.iter_records())
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    finally:
        os.unlink(tmp_path)

    attestation = _attestation_from_json(attestation_json)
    return _guarded_ingest(
        session,
        records,
        declared_provenance=desc.provenance,
        dataset_id=dataset_id or desc.dataset_id,
        attestation=attestation,
        source="eav_file",
    )


@router.post(
    "/records",
    response_model=RecordIngestResponse,
    dependencies=[Depends(require_role("service"))],
)
async def ingest_records_api(
    batch: RecordIngestBatch, session: Session = Depends(get_db)
) -> RecordIngestResponse:
    if len(batch.records) > _MAX_API_BATCH_RECORDS:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"batch of {len(batch.records)} exceeds the {_MAX_API_BATCH_RECORDS}-record bound "
            "per call (ARCH §5.2) — use /ingest/records/file or /ingest/records/eav for a "
            "larger push",
        )
    return _guarded_ingest(
        session,
        batch.records,
        declared_provenance=batch.dataset_provenance,
        dataset_id=None,
        # RecordIngestBatch carries no attestation field -> deidentified is rejected here.
        attestation=None,
        source="api",
    )
