"""Celery tasks for eval + question generation (ARCH §15, §16). Phase 2/3 bodies."""

from __future__ import annotations

from app.worker import celery_app


@celery_app.task(name="eval.generate_questions")
def generate_questions(count: int, composition: str = "60,20,20", seed: int | None = None) -> None:
    raise NotImplementedError("Phase 2 (ARCH §15)")


@celery_app.task(name="eval.run_harness")
def run_harness_task(snapshot: str = "latest") -> None:
    raise NotImplementedError("Phase 3 (ARCH §16)")
