"""persist_chunks: DB row creation (fake session) + real Qdrant upsert
(qdrant-client's embedded `:memory:` mode) with the offline stub embedder
(ARCH §5.1 steps 3-4; PRD-004)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.config import get_settings
from app.db.models.corpus import Chunk
from app.ingestion.chunk_persistence import persist_chunks
from app.retrieval.vectorstore import QdrantVectorStore


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
def _stub_embedding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store() -> QdrantVectorStore:
    s = QdrantVectorStore(url=":memory:", api_key="", collection="chunk_persist_test")
    s.ensure_collection(dense_dim=384)
    return s


def _chunk_dict(ordinal: int, *, parent_ordinal: int | None = None, **kw: object) -> dict:
    base = {
        "ordinal": ordinal,
        "section_path": "1 › Introduction",
        "section_number": "1",
        "heading": "Introduction",
        "page_start": 1,
        "page_end": 1,
        "char_start": ordinal * 100,
        "char_end": ordinal * 100 + 50,
        "chunk_type": "prose",
        "text": f"Chunk text number {ordinal} about neonatal sepsis.",
        "figure_ref": None,
        "token_count": 8,
        "parent_ordinal": parent_ordinal,
        "meta": {
            "embedding_text": f"Introduction\n\nChunk text number {ordinal} about neonatal sepsis."
        },
    }
    base.update(kw)
    return base


def test_persists_chunk_rows_and_upserts_to_qdrant(store: QdrantVectorStore) -> None:
    session = _FakeSession()
    document_version_id = uuid.uuid4()
    document_id = uuid.uuid4()

    rows = persist_chunks(
        session,
        store,
        document_version_id=document_version_id,
        document_id=document_id,
        document_title="Test Guideline",
        version_label="2024.1",
        effective_date=date(2024, 1, 1),
        chunk_dicts=[_chunk_dict(0), _chunk_dict(1, parent_ordinal=0)],
        document_topic_tags=["neonatal sepsis"],
    )

    assert len(rows) == 2
    assert all(isinstance(r, Chunk) for r in rows)
    assert rows[1].parent_chunk_id == rows[0].id  # resolved from parent_ordinal -> real id
    assert rows[0].parent_chunk_id is None
    assert rows[0].vector_id == str(rows[0].id)

    qdrant_rows = store.get_by_ids([str(r.id) for r in rows])
    assert len(qdrant_rows) == 2
    assert {r["chunk_id"] for r in qdrant_rows} == {str(rows[0].id), str(rows[1].id)}
    assert qdrant_rows[0]["document_title"] == "Test Guideline"
    assert qdrant_rows[0]["status"] == "active"


def test_topic_tags_assigned_from_document_topic_tags(store: QdrantVectorStore) -> None:
    session = _FakeSession()
    rows = persist_chunks(
        session,
        store,
        document_version_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="T",
        version_label="1.0",
        effective_date=None,
        chunk_dicts=[_chunk_dict(0)],
        document_topic_tags=["neonatal sepsis", "vitamin K prophylaxis"],
    )
    assert rows[0].meta["topic_tags"] == ["neonatal sepsis"]


def test_empty_chunk_list_is_a_noop(store: QdrantVectorStore) -> None:
    session = _FakeSession()
    rows = persist_chunks(
        session,
        store,
        document_version_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="T",
        version_label="1.0",
        effective_date=None,
        chunk_dicts=[],
        document_topic_tags=[],
    )
    assert rows == []
    assert session.added == []


def test_chunks_out_of_input_order_are_persisted_in_ordinal_order(store: QdrantVectorStore) -> None:
    session = _FakeSession()
    # deliberately pass ordinal 1 before ordinal 0
    rows = persist_chunks(
        session,
        store,
        document_version_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="T",
        version_label="1.0",
        effective_date=None,
        chunk_dicts=[_chunk_dict(1, parent_ordinal=0), _chunk_dict(0)],
        document_topic_tags=[],
    )
    ordinals = [r.ordinal for r in rows]
    assert ordinals == [0, 1]
    assert rows[1].parent_chunk_id == rows[0].id
