"""`/corpus/*` HTTP routes (PRD-004, PRD-005, PRD-016; ARCH §5.1).

Offline via FastAPI's TestClient: `get_db`/`current_principal` dependency-
overridden (a fake session; a clinician or admin principal). The underlying
`app.ingestion.corpus_access` functions are monkeypatched on the route module
so no real Postgres is needed — that module's own real behavior is covered
by `tests/test_corpus_access.py`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.routes.corpus as corpus_mod
from app.api.deps import Principal, current_principal, get_db
from app.ingestion.corpus_access import (
    ChunkNotFoundError,
    DocumentNotFoundError,
    DocumentVersionNotFoundError,
)
from app.main import app as fastapi_app

DOCUMENT_ID = str(uuid.uuid4())
VERSION_ID = str(uuid.uuid4())
CHUNK_ID = str(uuid.uuid4())


class _FakeSession:
    pass


class _FakeDoc:
    def __init__(self, id_: str) -> None:
        self.id = id_


def _client(role: str):
    def _fake_get_db():
        yield _FakeSession()

    def _principal() -> Principal:
        return Principal(
            user_id=str(uuid.uuid4()), roles=frozenset({role}), is_clinician=role == "clinician"
        )

    fastapi_app.dependency_overrides[get_db] = _fake_get_db
    fastapi_app.dependency_overrides[current_principal] = _principal
    return TestClient(fastapi_app)


@pytest.fixture
def clinician_client():
    client = _client("clinician")
    try:
        yield client
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def admin_client():
    client = _client("admin")
    try:
        yield client
    finally:
        fastapi_app.dependency_overrides.clear()


def test_list_documents_returns_documents_with_versions(
    clinician_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(corpus_mod, "list_documents", lambda session: [_FakeDoc(DOCUMENT_ID)])
    monkeypatch.setattr(
        corpus_mod, "_serialize_document", lambda d, versions: {"id": d.id, "versions": versions}
    )
    monkeypatch.setattr(corpus_mod, "list_document_versions", lambda session, doc_id: [])
    resp = clinician_client.get("/api/corpus/documents")
    assert resp.status_code == 200, resp.text
    assert resp.json() == [{"id": DOCUMENT_ID, "versions": []}]


def test_list_versions_returns_404_when_document_missing(
    clinician_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(session, doc_id):  # noqa: ANN001, ARG001
        raise DocumentNotFoundError("no such document")

    monkeypatch.setattr(corpus_mod, "list_document_versions", _raise)
    resp = clinician_client.get(f"/api/corpus/documents/{DOCUMENT_ID}/versions")
    assert resp.status_code == 404


def test_get_chunk_returns_404_when_missing(
    clinician_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(session, chunk_id):  # noqa: ANN001, ARG001
        raise ChunkNotFoundError("no such chunk")

    monkeypatch.setattr(corpus_mod, "get_chunk_row", _raise)
    resp = clinician_client.get(f"/api/corpus/chunks/{CHUNK_ID}")
    assert resp.status_code == 404


def test_get_chunk_returns_chunk_body(
    clinician_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Chunk:
        id = CHUNK_ID
        document_version_id = VERSION_ID
        section_path = None
        section_number = None
        heading = None
        page_start = 1
        page_end = 1
        char_start = 0
        char_end = 10
        ordinal = 0
        chunk_type = "prose"
        text = "hello"
        meta: dict = {}

    monkeypatch.setattr(corpus_mod, "get_chunk_row", lambda session, chunk_id: _Chunk())
    resp = clinician_client.get(f"/api/corpus/chunks/{CHUNK_ID}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["text"] == "hello"


def test_withdraw_version_requires_admin(clinician_client: TestClient) -> None:
    resp = clinician_client.post(f"/api/corpus/versions/{VERSION_ID}/withdraw")
    assert resp.status_code == 403


def test_withdraw_version_success(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Version:
        id = VERSION_ID
        document_id = DOCUMENT_ID
        version_label = "2024.1"
        effective_date = None
        ingested_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
        supersedes_id = None
        status = "withdrawn"
        content_sha256 = "a" * 64
        page_count = None
        format_profile = None
        parse_quality = None

    captured = {}

    def _fake_withdraw(session, version_id, **kwargs):  # noqa: ANN001, ARG001
        captured["kwargs"] = kwargs
        return _Version()

    monkeypatch.setattr(corpus_mod, "withdraw_version", _fake_withdraw)
    resp = admin_client.post(f"/api/corpus/versions/{VERSION_ID}/withdraw")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "withdrawn"
    assert captured["kwargs"]["actor_role"] == "admin"


def test_withdraw_version_404_when_missing(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(session, version_id, **kwargs):  # noqa: ANN001, ARG001
        raise DocumentVersionNotFoundError("no such version")

    monkeypatch.setattr(corpus_mod, "withdraw_version", _raise)
    resp = admin_client.post(f"/api/corpus/versions/{VERSION_ID}/withdraw")
    assert resp.status_code == 404
