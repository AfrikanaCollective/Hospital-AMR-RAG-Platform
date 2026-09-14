"""ingest_records: dedupe on MRN + encryption + field_index (ARCH §5.2;
DEVIATIONS #57). Offline via a fake session — `_find_patient_by_mrn_hash` is
the only DB read, monkeypatched so the real dedup/encryption/field-index
logic is exercised without a real Postgres."""

from __future__ import annotations

import uuid

import pytest

import app.ingestion.records as records_mod
from app.config import get_settings
from app.db.models.records import Patient
from app.ingestion.records import RealDataSuspectedError, compute_field_index, ingest_records
from app.schemas.record import SYNTHETIC_PROVENANCE, Encounter, Medication, PatientRecord


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@pytest.fixture(autouse=True)
def _dev_kek(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CRYPTO_KEK_FILE", str(tmp_path / "kek.bin"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _rec(mrn: str, **kw: object) -> PatientRecord:
    return PatientRecord(record_id=mrn, mrn=mrn, dataset_provenance=SYNTHETIC_PROVENANCE, **kw)


def test_ingest_creates_one_patient_and_one_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(records_mod, "_find_patient_by_mrn_hash", lambda session, h: None)
    session = _FakeSession()
    ids = ingest_records(session, [_rec("MRN-1")], declared_provenance=SYNTHETIC_PROVENANCE)
    assert len(ids) == 1
    patients = [o for o in session.added if isinstance(o, Patient)]
    assert len(patients) == 1
    assert patients[0].data_class == "synthetic"
    assert patients[0].mrn_enc != b"MRN-1"  # actually encrypted, not stored raw


def test_ingest_dedupes_existing_patient_by_mrn_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    existing_patient = Patient(
        mrn_enc=b"x", mrn_hash="irrelevant", source="file", data_class="synthetic"
    )
    existing_patient.id = uuid.uuid4()
    monkeypatch.setattr(
        records_mod, "_find_patient_by_mrn_hash", lambda session, h: existing_patient
    )

    session = _FakeSession()
    ingest_records(session, [_rec("MRN-1")], declared_provenance=SYNTHETIC_PROVENANCE)

    patients = [o for o in session.added if isinstance(o, Patient)]
    assert patients == []  # no new Patient row -- reused the existing one


def test_ingest_two_records_same_mrn_share_one_patient(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[Patient] = []
    real_lookup = records_mod._find_patient_by_mrn_hash

    def fake_lookup(session, mrn_hash):  # noqa: ANN001
        for p in created:
            if p.mrn_hash == mrn_hash:
                return p
        return None

    monkeypatch.setattr(records_mod, "_find_patient_by_mrn_hash", fake_lookup)

    class _TrackingSession(_FakeSession):
        def add(self, obj: object) -> None:
            super().add(obj)
            if isinstance(obj, Patient):
                created.append(obj)

    session = _TrackingSession()
    ingest_records(
        session, [_rec("MRN-1"), _rec("MRN-1")], declared_provenance=SYNTHETIC_PROVENANCE
    )
    assert len(created) == 1
    _ = real_lookup  # unused, kept for clarity that we intentionally replaced it


def test_ingest_rejects_unmarked_batch() -> None:
    with pytest.raises(RealDataSuspectedError):
        ingest_records(_FakeSession(), [_rec("MRN-1")], declared_provenance=None)


def test_field_index_has_no_values_only_presence() -> None:
    rec = _rec(
        "MRN-1",
        encounter=Encounter(ward="NBU", presenting_complaint="grunting"),
        medications=[Medication(name="ampicillin")],
    )
    idx = compute_field_index(rec)
    assert idx["encounter.ward"] is True
    assert idx["medications"] is True
    assert "ampicillin" not in str(idx.values())  # no leaked value anywhere
    assert "NBU" not in str(idx.values())
    assert idx.get("clinical_notes") is False  # absent field -> False, not omitted


def test_field_index_excludes_always_required_identity_fields() -> None:
    idx = compute_field_index(_rec("MRN-1"))
    assert "mrn" not in idx
    assert "record_id" not in idx
    assert "schema_version" not in idx


def test_field_index_reflects_empty_list_as_false() -> None:
    idx = compute_field_index(_rec("MRN-1"))
    assert idx["medications"] is False
    assert idx["problems"] is False
