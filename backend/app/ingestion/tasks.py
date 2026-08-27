"""Celery ingestion tasks (ARCH §5; PRD-105). Phase 2 implements bodies."""

from __future__ import annotations

from app.worker import celery_app


@celery_app.task(name="ingestion.process_document")
def process_document(document_version_id: str) -> None:
    """parse -> chunk -> embed -> upsert Qdrant -> topic index (ARCH §5.1)."""
    raise NotImplementedError("Phase 2")


@celery_app.task(name="ingestion.process_record_batch")
def process_record_batch(batch_id: str) -> None:
    raise NotImplementedError("Phase 2")


@celery_app.task(name="ingestion.reembed_corpus")
def reembed_corpus(new_collection: str) -> None:
    """Full re-embed into a new Qdrant collection on EMBEDDING_MODEL_ID change (ARCH §6)."""
    raise NotImplementedError("Phase 2")
