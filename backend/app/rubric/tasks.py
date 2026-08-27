"""Celery tasks for the rubric workflow (ARCH §14; PRD-042).

- compute_result_irr_and_archive: fired when a result reaches IRR_MIN_RATERS.
- compute_slice_irr: manual/triggered corpus-level IRR over an explicit slice
  (never pools provenance by default — PRD-046).
Phase 3 implements.
"""

from __future__ import annotations

from app.worker import celery_app


@celery_app.task(name="rubric.compute_result_irr_and_archive")
def compute_result_irr_and_archive(result_id: str) -> None:
    raise NotImplementedError("Phase 3 (ARCH §14.4, §14.5)")


@celery_app.task(name="rubric.compute_slice_irr")
def compute_slice_irr(slice_definition: dict) -> None:
    raise NotImplementedError("Phase 3 (ARCH §14.4 — irr_batch)")
