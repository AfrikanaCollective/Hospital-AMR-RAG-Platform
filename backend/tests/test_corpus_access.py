"""Corpus read access + withdrawal (ARCH §5.1; PRD-004, PRD-005)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import app.audit.log as audit_log
from app.db.models.corpus import Chunk, Document, DocumentVersion
from app.ingestion import corpus_access as access

DOCUMENT_ID = uuid.uuid4()
VERSION_ID = uuid.uuid4()
CHUNK_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, *, documents=None, versions=None, chunks=None) -> None:  # noqa: ANN001
        self._documents = documents or []
        self._versions = versions or []
        self._chunks = chunks or []
        self.added: list = []

    def get(self, model, id_):  # noqa: ANN001
        rows = {Document: self._documents, DocumentVersion: self._versions, Chunk: self._chunks}[
            model
        ]
        return next((r for r in rows if r.id == id_), None)

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def execute(self, stmt):  # noqa: ANN001
        entity = stmt.column_descriptions[0]["entity"]

        class _Res:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Res:
                return self

            def all(self) -> list:
                return self._rows

        if entity is Document:
            return _Res(self._documents)
        return _Res(self._versions)


def _document() -> Document:
    return Document(id=DOCUMENT_ID, title="Neonatal Sepsis Guideline", classification="public")


def _version(status: str = "active") -> DocumentVersion:
    return DocumentVersion(
        id=VERSION_ID,
        document_id=DOCUMENT_ID,
        version_label="2024.1",
        ingested_at=datetime.now(UTC),
        status=status,
        content_sha256="a" * 64,
    )


def _chunk() -> Chunk:
    return Chunk(
        id=CHUNK_ID,
        document_version_id=VERSION_ID,
        page_start=1,
        page_end=1,
        char_start=0,
        char_end=10,
        ordinal=0,
        chunk_type="prose",
        text="Some guideline text.",
        meta={},
    )


def test_list_documents_returns_all() -> None:
    session = _FakeSession(documents=[_document()])
    docs = access.list_documents(session)
    assert [d.id for d in docs] == [DOCUMENT_ID]


def test_list_document_versions_returns_versions_for_document() -> None:
    session = _FakeSession(documents=[_document()], versions=[_version()])
    versions = access.list_document_versions(session, DOCUMENT_ID)
    assert [v.id for v in versions] == [VERSION_ID]


def test_list_document_versions_raises_when_document_missing() -> None:
    import pytest

    session = _FakeSession()
    with pytest.raises(access.DocumentNotFoundError):
        access.list_document_versions(session, DOCUMENT_ID)


def test_get_chunk_returns_chunk_regardless_of_version_status() -> None:
    session = _FakeSession(chunks=[_chunk()])
    chunk = access.get_chunk(session, CHUNK_ID)
    assert chunk.id == CHUNK_ID


def test_get_chunk_raises_when_missing() -> None:
    import pytest

    session = _FakeSession()
    with pytest.raises(access.ChunkNotFoundError):
        access.get_chunk(session, CHUNK_ID)


def test_withdraw_version_sets_status_and_audits(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession(versions=[_version()])
    actor_id = uuid.uuid4()

    result = access.withdraw_version(session, VERSION_ID, actor_id=actor_id, actor_role="admin")
    assert result.status == "withdrawn"
    assert len(session.added) == 1
    audit_event = session.added[0]
    assert audit_event.action == "config_change"
    assert audit_event.outcome == "withdrawn"
    assert audit_event.detail == {
        "document_version_id": str(VERSION_ID),
        "document_id": str(DOCUMENT_ID),
    }


def test_withdraw_version_raises_when_missing() -> None:
    import pytest

    session = _FakeSession()
    with pytest.raises(access.DocumentVersionNotFoundError):
        access.withdraw_version(session, VERSION_ID)


def test_withdraw_version_is_idempotent(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession(versions=[_version(status="withdrawn")])
    result = access.withdraw_version(session, VERSION_ID)
    assert result.status == "withdrawn"
