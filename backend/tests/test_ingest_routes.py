"""`/ingest/*` HTTP routes (ARCH §5, ARCH-038, ARCH-039).

Offline via FastAPI's TestClient: `get_db` and `current_principal` are
dependency-overridden (a fake session; an admin/service principal, or for
`anonymous_client` a bare clinician principal to exercise wrong-role 403s).
The same DB-read indirection points used by the offline unit tests
for `ingest_records`/`create_or_supersede_document_version` are monkeypatched
here too, so no real Postgres is needed. `process_document.delay` is
monkeypatched so no real Celery/Redis broker is needed.
"""

from __future__ import annotations

import json
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

import app.audit.log as audit_log
import app.ingestion.documents as documents_mod
import app.ingestion.records as records_mod
from app.api.deps import Principal, current_principal, get_db
from app.config import get_settings
from app.db.models.corpus import DocumentVersion
from app.main import app as fastapi_app
from app.schemas.record import DEIDENTIFIED_PROVENANCE, SYNTHETIC_PROVENANCE


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@pytest.fixture
def fake_session() -> _FakeSession:
    return _FakeSession()


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch: pytest.MonkeyPatch):
    # Never write test uploads into the real repo corpus dir.
    monkeypatch.setenv("SAMPLE_GUIDELINES_DIR", str(tmp_path / "guidelines"))
    monkeypatch.setenv("PATIENT_RECORDS_DIR", str(tmp_path / "patient_records"))
    monkeypatch.setenv("CRYPTO_KEK_FILE", str(tmp_path / "kek.bin"))
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_real_audit_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)


@pytest.fixture(autouse=True)
def _no_document_lookups(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(documents_mod, "_find_version_by_sha256", lambda s, sha: None)
    monkeypatch.setattr(documents_mod, "_find_document_by_external_ref", lambda s, ref: None)
    monkeypatch.setattr(documents_mod, "_find_active_versions", lambda s, doc_id: [])


@pytest.fixture(autouse=True)
def _no_patient_lookups(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(records_mod, "_find_patient_by_mrn_hash", lambda s, h: None)


@pytest.fixture
def client(fake_session: _FakeSession):
    def _fake_get_db():
        yield fake_session

    def _admin_service_principal() -> Principal:
        return Principal(user_id="test-admin", roles=frozenset({"admin", "service"}))

    fastapi_app.dependency_overrides[get_db] = _fake_get_db
    fastapi_app.dependency_overrides[current_principal] = _admin_service_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(fake_session: _FakeSession):
    """Authenticated as a clinician (wrong role for admin/service-only routes) ->
    exercises `require_role`'s 403 path, not `current_principal`'s 401 path.
    Phase 4 removed the permissive no-token dev fallback (`app/api/deps.py`),
    so a route under this fixture must still resolve to *some* principal to
    reach the role check at all; a bare clinician role is the minimal one."""

    def _fake_get_db():
        yield fake_session

    def _clinician_principal() -> Principal:
        return Principal(
            user_id="test-clinician", roles=frozenset({"clinician"}), is_clinician=True
        )

    fastapi_app.dependency_overrides[get_db] = _fake_get_db
    fastapi_app.dependency_overrides[current_principal] = _clinician_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


# ── POST /ingest/documents ───────────────────────────────────────────────────


def test_ingest_document_requires_admin_role(anonymous_client: TestClient) -> None:
    resp = anonymous_client.post(
        "/api/ingest/documents",
        data={"title": "T", "version_label": "1.0"},
        files={"file": ("g.md", b"# Heading\n\nSome text.", "text/markdown")},
    )
    assert resp.status_code == 403


def test_ingest_document_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path, fake_session: _FakeSession
) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.routes.ingest.process_document.delay",
        lambda *a, **kw: calls.append((a, kw)),
    )
    resp = client.post(
        "/api/ingest/documents",
        data={
            "title": "Synthetic Guideline",
            "version_label": "2024.1",
            "publisher": "Test Org",
            "topic_tags": ["neonatal sepsis"],
        },
        files={"file": ("guideline.md", b"# Heading\n\nSome guideline text.", "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] is True
    assert body["processing_enqueued"] is True
    assert body["version_status"] == "active"
    assert len(calls) == 1
    assert (get_settings().sample_guidelines_dir + "/guideline.md").endswith("guideline.md")

    audit_events = [
        obj for obj in fake_session.added if getattr(obj, "action", None) == "ingestion"
    ]
    assert len(audit_events) == 1
    assert audit_events[0].actor_role == "admin"
    assert audit_events[0].outcome == "created"
    assert audit_events[0].detail["kind"] == "document"


def test_ingest_document_rejects_unsupported_extension(client: TestClient) -> None:
    resp = client.post(
        "/api/ingest/documents",
        data={"title": "T", "version_label": "1.0"},
        files={"file": ("guideline.exe", b"not a guideline", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_ingest_document_rejects_empty_upload(client: TestClient) -> None:
    resp = client.post(
        "/api/ingest/documents",
        data={"title": "T", "version_label": "1.0"},
        files={"file": ("guideline.md", b"", "text/markdown")},
    )
    assert resp.status_code == 400


def test_ingest_document_conflicting_filename_is_409(client: TestClient) -> None:
    guidelines_dir = get_settings().sample_guidelines_dir
    import pathlib

    pathlib.Path(guidelines_dir).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(guidelines_dir) / "guideline.md").write_bytes(b"# Original content")

    resp = client.post(
        "/api/ingest/documents",
        data={"title": "T", "version_label": "1.0"},
        files={"file": ("guideline.md", b"# Completely different content", "text/markdown")},
    )
    assert resp.status_code == 409


def test_ingest_document_idempotent_resubmit_does_not_enqueue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = DocumentVersion(
        document_id=uuid.uuid4(), version_label="2024.1", status="active", content_sha256="x"
    )
    existing.id = uuid.uuid4()
    monkeypatch.setattr(documents_mod, "_find_version_by_sha256", lambda s, sha: existing)
    calls = []
    monkeypatch.setattr(
        "app.api.routes.ingest.process_document.delay",
        lambda *a, **kw: calls.append((a, kw)),
    )

    resp = client.post(
        "/api/ingest/documents",
        data={"title": "T", "version_label": "1.0"},
        files={"file": ("guideline.md", b"# Some content", "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] is False
    assert resp.json()["processing_enqueued"] is False
    assert calls == []


# ── POST /ingest/records/file ────────────────────────────────────────────────


def test_ingest_records_file_json_success(client: TestClient) -> None:
    payload = json.dumps([{"record_id": "1", "mrn": "MRN-1"}]).encode()
    resp = client.post(
        "/api/ingest/records/file",
        data={"declared_provenance": SYNTHETIC_PROVENANCE},
        files={"file": ("patients.json", payload, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["data_class"] == "synthetic"


def test_ingest_records_file_rejects_unmarked_batch(client: TestClient) -> None:
    payload = json.dumps([{"record_id": "1", "mrn": "MRN-1"}]).encode()
    resp = client.post(
        "/api/ingest/records/file",
        data={"declared_provenance": "not-a-real-marker"},
        files={"file": ("patients.json", payload, "application/json")},
    )
    assert resp.status_code == 400


def test_ingest_records_file_invalid_csv_list_column_is_422(client: TestClient) -> None:
    csv_text = b"record_id,mrn,medications\n1,MRN-1,amoxicillin\n"
    resp = client.post(
        "/api/ingest/records/file",
        data={"declared_provenance": SYNTHETIC_PROVENANCE},
        files={"file": ("patients.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 422


def test_ingest_records_file_deidentified_with_attestation_succeeds(client: TestClient) -> None:
    payload = json.dumps([{"record_id": "1", "mrn": "MRN-1"}]).encode()
    attestation = {
        "source": "s",
        "collection_period": "2024",
        "site": "site",
        "deidentification_method": "m",
        "deidentification_standard": "std",
        "consent_basis": "c",
        "licence": "l",
        "attested_by": "a",
        "attested_date": "2024-01-01",
    }
    resp = client.post(
        "/api/ingest/records/file",
        data={
            "declared_provenance": DEIDENTIFIED_PROVENANCE,
            "attestation_json": json.dumps(attestation),
        },
        files={"file": ("patients.json", payload, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data_class"] == "deidentified"


def test_ingest_records_file_deidentified_without_attestation_is_400(client: TestClient) -> None:
    payload = json.dumps([{"record_id": "1", "mrn": "MRN-1"}]).encode()
    resp = client.post(
        "/api/ingest/records/file",
        data={"declared_provenance": DEIDENTIFIED_PROVENANCE},
        files={"file": ("patients.json", payload, "application/json")},
    )
    assert resp.status_code == 400


# ── POST /ingest/records/eav ─────────────────────────────────────────────────


def _write_mapping(tmp_path, dataset_id: str, *, provenance: str = SYNTHETIC_PROVENANCE) -> None:
    mapping_dir = tmp_path / "patient_records" / "deidentified" / dataset_id
    mapping_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "dataset_id": dataset_id,
        "provenance": provenance,
        "schema_version": "1.3.0",
        "identity": {"record_id": "{key}", "mrn": "DEID-{key}"},
        "fields": {"ward": {"target": "encounter.ward", "transform": "identity"}},
    }
    (mapping_dir / "field_mapping.yaml").write_text(yaml.safe_dump(spec))


def test_ingest_records_eav_success(client: TestClient, tmp_path) -> None:
    _write_mapping(tmp_path, "test_ds")
    csv_text = b"key,field_name,field_value,context\n1,ward,NBU,\n"
    resp = client.post(
        "/api/ingest/records/eav",
        data={"mapping_ref": "test_ds"},
        files={"file": ("eav.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1
    assert resp.json()["data_class"] == "synthetic"


def test_ingest_records_eav_unknown_mapping_ref_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/ingest/records/eav",
        data={"mapping_ref": "does-not-exist"},
        files={"file": ("eav.csv", b"key,field_name,field_value,context\n", "text/csv")},
    )
    assert resp.status_code == 404


def test_ingest_records_eav_deidentified_requires_attestation(client: TestClient, tmp_path) -> None:
    _write_mapping(tmp_path, "test_ds_deid", provenance=DEIDENTIFIED_PROVENANCE)
    csv_text = b"key,field_name,field_value,context\n1,ward,NBU,\n"
    resp = client.post(
        "/api/ingest/records/eav",
        data={"mapping_ref": "test_ds_deid"},
        files={"file": ("eav.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 400


# ── POST /ingest/records (API/service) ───────────────────────────────────────


def test_ingest_records_api_success(client: TestClient, fake_session: _FakeSession) -> None:
    resp = client.post(
        "/api/ingest/records",
        json={
            "dataset_provenance": SYNTHETIC_PROVENANCE,
            "records": [{"record_id": "1", "mrn": "MRN-1"}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1

    audit_events = [
        obj for obj in fake_session.added if getattr(obj, "action", None) == "ingestion"
    ]
    assert len(audit_events) == 1
    assert audit_events[0].actor_role == "service"
    assert audit_events[0].detail == {
        "kind": "records",
        "source": "api",
        "data_class": "synthetic",
        "dataset_id": None,
        "count": 1,
    }


def test_ingest_records_api_batch_too_large_is_413(client: TestClient) -> None:
    records = [{"record_id": str(i), "mrn": f"MRN-{i}"} for i in range(501)]
    resp = client.post(
        "/api/ingest/records",
        json={"dataset_provenance": SYNTHETIC_PROVENANCE, "records": records},
    )
    assert resp.status_code == 413


def test_ingest_records_api_deidentified_has_no_attestation_field_and_is_rejected(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/ingest/records",
        json={
            "dataset_provenance": DEIDENTIFIED_PROVENANCE,
            "records": [{"record_id": "1", "mrn": "MRN-1"}],
        },
    )
    assert resp.status_code == 400


def test_ingest_records_api_requires_service_role(anonymous_client: TestClient) -> None:
    resp = anonymous_client.post(
        "/api/ingest/records",
        json={"dataset_provenance": SYNTHETIC_PROVENANCE, "records": []},
    )
    assert resp.status_code == 403
