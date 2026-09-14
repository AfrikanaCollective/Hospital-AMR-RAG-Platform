"""`/records/*` HTTP routes (PRD-080, PRD-084; ARCH §4.2, ARCH-034).

Offline via FastAPI's TestClient: `get_patient_scoped_db`/`current_principal`
dependency-overridden (a fake session; a clinician principal). `list_record_fields`/
`get_patient_fields` are monkeypatched on the route module so no real Postgres/
crypto is needed. One test instead monkeypatches `app.api.deps.session_scope`
and leaves the real `get_patient_scoped_db` in place, to prove FastAPI actually
binds that dependency's `patient_id` parameter from the route's own
`{patient_id}` path parameter (DEVIATIONS.md #88) — not just assumed.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.deps as deps_mod
import app.api.routes.records as records_mod
from app.api.deps import Principal, current_principal, get_patient_scoped_db
from app.main import app as fastapi_app
from app.records.access import PatientNotFoundError

PATIENT_ID = str(uuid.uuid4())


class _FakeSession:
    pass


@pytest.fixture
def client():
    def _fake_scoped_db(patient_id: str):  # noqa: ARG001
        yield _FakeSession()

    def _clinician_principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()), roles=frozenset({"clinician"}), is_clinician=True
        )

    fastapi_app.dependency_overrides[get_patient_scoped_db] = _fake_scoped_db
    fastapi_app.dependency_overrides[current_principal] = _clinician_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client():
    """A real (non-clinician) role -> exercises `require_role`'s 403 path."""

    def _fake_scoped_db(patient_id: str):  # noqa: ARG001
        yield _FakeSession()

    def _reviewer_principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()), roles=frozenset({"reviewer"}), is_clinician=False
        )

    fastapi_app.dependency_overrides[get_patient_scoped_db] = _fake_scoped_db
    fastapi_app.dependency_overrides[current_principal] = _reviewer_principal
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


def test_list_fields_returns_names(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        records_mod,
        "list_record_fields",
        lambda session, pid: ["a.b", "c.d"],  # noqa: ARG005
    )
    resp = client.get(f"/api/records/{PATIENT_ID}/fields")
    assert resp.status_code == 200, resp.text
    assert resp.json() == ["a.b", "c.d"]


def test_list_fields_requires_clinician(anonymous_client: TestClient) -> None:
    resp = anonymous_client.get(f"/api/records/{PATIENT_ID}/fields")
    assert resp.status_code == 403


def test_list_fields_404_when_patient_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(session, pid):  # noqa: ANN001, ARG001
        raise PatientNotFoundError("no record")

    monkeypatch.setattr(records_mod, "list_record_fields", _raise)
    resp = client.get(f"/api/records/{PATIENT_ID}/fields")
    assert resp.status_code == 404


def test_get_fields_requires_purpose_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(records_mod, "get_patient_fields", lambda *a, **k: {})  # noqa: ARG005
    resp = client.get(f"/api/records/{PATIENT_ID}", params={"fields": "a.b"})
    assert resp.status_code == 400


def test_get_fields_returns_values_and_threads_purpose_and_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    def _fake_get_fields(session, patient_id, paths, **kwargs):  # noqa: ANN001, ARG001
        captured["paths"] = paths
        captured["kwargs"] = kwargs
        return {p: 1 for p in paths}

    monkeypatch.setattr(records_mod, "get_patient_fields", _fake_get_fields)
    resp = client.get(
        f"/api/records/{PATIENT_ID}",
        params={"fields": "vitals.heart_rate_bpm, encounter.gestational_age_weeks"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"vitals.heart_rate_bpm": 1, "encounter.gestational_age_weeks": 1}
    assert captured["paths"] == ["vitals.heart_rate_bpm", "encounter.gestational_age_weeks"]
    assert captured["kwargs"]["purpose"] == "clinical_care"
    assert captured["kwargs"]["actor_role"] == "clinician"


def test_get_fields_404_when_patient_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(session, patient_id, paths, **kwargs):  # noqa: ANN001, ARG001
        raise PatientNotFoundError("no record")

    monkeypatch.setattr(records_mod, "get_patient_fields", _raise)
    resp = client.get(
        f"/api/records/{PATIENT_ID}",
        params={"fields": "a.b"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 404


def test_get_fields_requires_clinician(anonymous_client: TestClient) -> None:
    resp = anonymous_client.get(
        f"/api/records/{PATIENT_ID}",
        params={"fields": "a.b"},
        headers={"X-Purpose-Of-Use": "clinical_care"},
    )
    assert resp.status_code == 403


def test_patient_scoped_db_binds_patient_id_from_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real `get_patient_scoped_db` (not overridden) + a fake `session_scope`
    proves FastAPI feeds it the route's own `{patient_id}` path segment."""
    captured = {}

    def _fake_session_scope(patient_scope: str | None = None):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            captured["patient_scope"] = patient_scope
            yield _FakeSession()

        return _cm()

    monkeypatch.setattr(deps_mod, "session_scope", _fake_session_scope)
    monkeypatch.setattr(records_mod, "list_record_fields", lambda session, pid: [])  # noqa: ARG005

    def _clinician_principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()), roles=frozenset({"clinician"}), is_clinician=True
        )

    fastapi_app.dependency_overrides[current_principal] = _clinician_principal
    try:
        resp = TestClient(fastapi_app).get(f"/api/records/{PATIENT_ID}/fields")
    finally:
        fastapi_app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    assert captured["patient_scope"] == PATIENT_ID
