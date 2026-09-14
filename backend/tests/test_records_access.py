"""Patient-record read access (ARCH §4.2, §10.2; DEVIATIONS.md #70)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.audit.log as audit_log
from app.crypto.provider import get_crypto
from app.db.models.records import PatientRecord as PatientRecordRow
from app.records import access
from app.schemas.record import Encounter, LabResult, PatientRecord, Vitals

PATIENT_ID = uuid.uuid4()


def _make_record_row() -> PatientRecordRow:
    record = PatientRecord(
        record_id="r1",
        mrn="MRN-1",
        given_name="Baby",
        family_name="Test",
        encounter=Encounter(gestational_age_weeks=32.0, day_of_life=2),
        vitals=[
            Vitals(recorded_at=datetime(2026, 1, 1, tzinfo=UTC), heart_rate_bpm=150.0),
            Vitals(recorded_at=datetime(2026, 1, 2, tzinfo=UTC), heart_rate_bpm=170.0),
        ],
        labs=[LabResult(analyte="CRP", value=12.0, collected_at=datetime(2026, 1, 1, tzinfo=UTC))],
    )
    crypto = get_crypto()
    row = PatientRecordRow(
        id=uuid.uuid4(),
        patient_id=PATIENT_ID,
        schema_version=record.schema_version,
        ingested_at=datetime.now(UTC),
        payload_enc=crypto.encrypt(
            record.model_dump_json().encode("utf-8"), aad=str(PATIENT_ID).encode()
        ),
        field_index={"vitals.0.heart_rate_bpm": True, "encounter.gestational_age_weeks": True},
    )
    return row


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass


def test_extract_features_uses_latest_vitals() -> None:
    row = _make_record_row()
    record = access.decrypt_record(row)
    features = access.extract_features(record)
    assert features["vitals.heart_rate_bpm"] == 170.0  # latest, not first
    assert features["encounter.gestational_age_weeks"] == 32.0
    assert features["labs.CRP"] == 12.0
    assert "given_name" not in features  # identity fields excluded


def test_get_patient_fields_returns_only_requested_and_audits(monkeypatch) -> None:  # noqa: ANN001
    row = _make_record_row()
    monkeypatch.setattr(access, "_find_latest_patient_record", lambda session, pid: row)
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()

    result = access.get_patient_fields(
        session,
        PATIENT_ID,
        ["vitals.heart_rate_bpm", "encounter.gestational_age_weeks"],
        purpose="clinical_care",
    )
    assert result == {"vitals.heart_rate_bpm": 170.0, "encounter.gestational_age_weeks": 32.0}
    assert len(session.added) == 1
    audit_event = session.added[0]
    assert audit_event.action == "record_access"
    assert audit_event.record_fields == ["vitals.heart_rate_bpm", "encounter.gestational_age_weeks"]
    assert audit_event.patient_id == PATIENT_ID


def test_get_patient_fields_never_returns_identity_fields(monkeypatch) -> None:  # noqa: ANN001
    row = _make_record_row()
    monkeypatch.setattr(access, "_find_latest_patient_record", lambda session, pid: row)
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)

    result = access.get_patient_fields(
        _FakeSession(),
        PATIENT_ID,
        ["given_name", "mrn", "vitals.heart_rate_bpm"],
        purpose="clinical_care",
    )
    assert "given_name" not in result
    assert "mrn" not in result
    assert result == {"vitals.heart_rate_bpm": 170.0}


def test_list_record_fields_uses_field_index_only(monkeypatch) -> None:  # noqa: ANN001
    row = _make_record_row()
    monkeypatch.setattr(access, "_find_latest_patient_record", lambda session, pid: row)
    fields = access.list_record_fields(_FakeSession(), PATIENT_ID)
    assert fields == ["encounter.gestational_age_weeks", "vitals.0.heart_rate_bpm"]


def test_missing_patient_raises(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(access, "_find_latest_patient_record", lambda session, pid: None)
    import pytest

    with pytest.raises(access.PatientNotFoundError):
        access.list_record_fields(_FakeSession(), PATIENT_ID)
