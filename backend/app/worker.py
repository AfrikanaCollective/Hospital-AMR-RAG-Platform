"""Celery application (ARCH-007; PRD-105).

Hosts: document ingestion + embedding, long-running agent runs, the eval
harness, IRR computation, and the auto-question generator. Task bodies live in
the owning packages (`app.ingestion.tasks`, `app.eval.tasks`, `app.rubric.tasks`).

Phase 1: app object + task module registration only.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "hospital_rag",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=[
        "app.ingestion.tasks",
        "app.eval.tasks",
        "app.rubric.tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # long tasks; avoid hoarding
)
