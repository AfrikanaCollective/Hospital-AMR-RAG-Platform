"""De-identified record source for auto-seeding the review queue
(ARCH §15.1 step 2; DEVIATIONS.md #113).

Loads already-ingested, attested de-identified patient records
(`records.patient` where `data_class = 'deidentified'`) for
`app.eval.auto_seed`. Does NOT ingest anything itself — a batch only shows up
here after an operator has run `scripts/ingest_deidentified_records.py
--attest-deidentified --persist` separately; this module only ever reads.

Opens its session with no `patient_scope` set (the row-level-security
policies on `records.*` — `ba3c23a19ce9_initial_schema.py` — allow all rows
when the `app.current_patient_scope` GUC is unset), unlike
`app.records.access` which always scopes to exactly one `patient_id` for a
live clinical request. This is a system/batch job that legitimately needs to
read across many patients' records to pick generation source material, not a
clinician acting for one patient — the same trust level as
`scripts/seed_db.py`, not a clinician-facing PHI read (which stays gated by
`app.records.access.get_patient_fields`'s field-policy logic; this module
never applies it, and its output never reaches an HTTP response — only the
internal question-generation prompt, sent only to the self-hosted gateway).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.crypto.provider import get_crypto
from app.db.models.records import Patient
from app.db.models.records import PatientRecord as PatientRecordRow
from app.schemas.enums import DataClass
from app.schemas.record import PatientRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def load_deidentified_records(
    session: Session, *, dataset_id: str | None = None
) -> list[tuple[uuid.UUID, dict]]:
    """Every de-identified patient's latest record snapshot, decrypted, as
    `(patient_id, plain record dict)`. One entry per patient — `patient` is
    already deduped on MRN at ingest (ARCH §5.2, DEVIATIONS.md #57), and
    `patient_record` is an append-only snapshot log, so a patient can have
    more than one row; only the most recently ingested is used here.
    `dataset_id` optionally narrows to one ingested batch
    (`patient_record.dataset_id`, e.g. `"newborn_nbu_2021"`)."""
    stmt = (
        select(PatientRecordRow, Patient)
        .join(Patient, PatientRecordRow.patient_id == Patient.id)
        .where(Patient.data_class == DataClass.DEIDENTIFIED.value)
        .order_by(PatientRecordRow.patient_id, PatientRecordRow.ingested_at.desc())
    )
    if dataset_id:
        stmt = stmt.where(PatientRecordRow.dataset_id == dataset_id)

    crypto = get_crypto()
    out: list[tuple[uuid.UUID, dict]] = []
    seen: set[uuid.UUID] = set()
    for row, patient in session.execute(stmt).all():
        if patient.id in seen:
            continue  # keep only the latest snapshot per patient
        seen.add(patient.id)
        plaintext = crypto.decrypt(row.payload_enc, aad=str(row.patient_id).encode("utf-8"))
        record = PatientRecord.model_validate_json(plaintext)
        out.append((patient.id, record.model_dump(mode="json")))
    return out
