"""De-identified record loading for review-queue auto-seeding (DEVIATIONS.md #113)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.crypto.provider import get_crypto
from app.db.models.records import Patient
from app.db.models.records import PatientRecord as PatientRecordRow
from app.eval.deidentified_source import load_deidentified_records
from app.schemas.record import PatientRecord


def _patient(data_class: str = "deidentified") -> Patient:
    return Patient(
        id=uuid.uuid4(),
        mrn_enc=b"irrelevant",
        mrn_hash="irrelevant",
        source="file",
        data_class=data_class,
    )


def _row(
    patient: Patient,
    *,
    record_id: str,
    ingested_at: datetime,
    dataset_id: str | None = None,
) -> PatientRecordRow:
    record = PatientRecord(record_id=record_id, mrn="MRN-X", sex="female")
    crypto = get_crypto()
    return PatientRecordRow(
        id=uuid.uuid4(),
        patient_id=patient.id,
        schema_version=record.schema_version,
        ingested_at=ingested_at,
        payload_enc=crypto.encrypt(
            record.model_dump_json().encode("utf-8"), aad=str(patient.id).encode()
        ),
        field_index={},
        dataset_id=dataset_id,
    )


class _FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def execute(self, stmt: object) -> _FakeResult:  # noqa: ARG002
        return _FakeResult(self._rows)


def test_decrypts_and_returns_one_entry_per_patient() -> None:
    p1 = _patient()
    p2 = _patient()
    # Two snapshots for p1, newest first (as the real ORDER BY would give) —
    # only the first one seen for a given patient should be kept.
    rows = [
        (_row(p1, record_id="newest", ingested_at=datetime(2026, 2, 1, tzinfo=UTC)), p1),
        (_row(p1, record_id="oldest", ingested_at=datetime(2026, 1, 1, tzinfo=UTC)), p1),
        (_row(p2, record_id="other-patient", ingested_at=datetime(2026, 1, 1, tzinfo=UTC)), p2),
    ]
    session = _FakeSession(rows)
    out = load_deidentified_records(session)
    by_patient = dict(out)
    assert len(out) == 2
    assert by_patient[p1.id]["record_id"] == "newest"
    assert by_patient[p2.id]["record_id"] == "other-patient"
