"""_run_process_document: the real parse -> chunk -> embed -> persist -> upsert
pipeline (ARCH §5.1), run against a real `.md` fixture, qdrant-client's
embedded `:memory:` mode, and the offline stub embedder — a fake session
(supporting `.get`/`.add`/`.flush`) stands in for Postgres."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.models.corpus import Document, DocumentVersion
from app.ingestion.tasks import _run_process_document
from app.retrieval.vectorstore import QdrantVectorStore

FIXTURES = Path(__file__).parent / "fixtures" / "guidelines"


class _FakeSession:
    def __init__(self, objects: dict) -> None:
        self.added: list = []
        self._objects = objects

    def get(self, cls: type, pk: object) -> object | None:
        return self._objects.get((cls, pk))

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@pytest.fixture(autouse=True)
def _stub_embedding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="process_document_test")
    s.ensure_collection(dense_dim=384)
    return s


def _seeded_session() -> tuple[_FakeSession, DocumentVersion]:
    document = Document(
        title="SYNTH-GL-002",
        publisher="Test",
        source_uri=str(FIXTURES / "SYNTH-GL-002_hospital_acquired_infection.md"),
    )
    document.id = uuid.uuid4()
    version = DocumentVersion(
        document_id=document.id,
        version_label="2024.2",
        content_sha256="deadbeef",
        status="active",
        format_profile="grade_recommendations",
    )
    version.id = uuid.uuid4()
    session = _FakeSession(
        {(Document, document.id): document, (DocumentVersion, version.id): version}
    )
    return session, version


def test_process_document_persists_chunks_and_updates_version(store: QdrantVectorStore) -> None:
    session, version = _seeded_session()

    rows = _run_process_document(
        session, str(version.id), topic_tags=["hospital-acquired infection"], vectorstore=store
    )

    assert len(rows) > 0
    assert any(r.chunk_type == "recommendation" for r in rows)
    assert version.page_count is not None
    assert version.parse_quality == 1.0  # markdown source -> fully extractable

    qdrant_rows = store.get_by_ids([str(r.id) for r in rows])
    assert len(qdrant_rows) == len(rows)


def test_process_document_raises_for_unknown_version() -> None:
    session = _FakeSession({})
    with pytest.raises(ValueError, match="not found"):
        _run_process_document(session, str(uuid.uuid4()))


def test_process_document_raises_when_document_has_no_source_uri() -> None:
    document = Document(title="No file")
    document.id = uuid.uuid4()
    version = DocumentVersion(
        document_id=document.id, version_label="1.0", content_sha256="x", status="active"
    )
    version.id = uuid.uuid4()
    session = _FakeSession(
        {(Document, document.id): document, (DocumentVersion, version.id): version}
    )
    with pytest.raises(ValueError, match="source_uri"):
        _run_process_document(session, str(version.id))
