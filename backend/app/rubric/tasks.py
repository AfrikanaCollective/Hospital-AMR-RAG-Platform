"""Celery tasks for the rubric workflow (ARCH §14; PRD-042).

- compute_result_irr_and_archive: fired when a result reaches IRR_MIN_RATERS.
  Redundant with the inline call `app.rubric.workflow.submit_rating` already
  makes when the threshold is crossed synchronously — this task exists so a
  slice-level recompute (or a manual admin trigger) can force it without
  going through the submit path again; it is idempotent (recomputing IRR and
  re-writing the archive row is safe to repeat).
- compute_slice_irr: manual/triggered corpus-level IRR over an explicit slice
  (never pools provenance by default — PRD-046), persisted as `eval.irr_batch`.

Real logic lives in plain, session-taking functions (`_run_compute_slice_irr`,
and `app.rubric.workflow.compute_result_irr_and_archive`); the `@celery_app.task`
wrappers only open a session — same split as `app.ingestion.tasks` — so tests
exercise the real logic without a Celery/Redis broker.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models.eval import IRRBatch, Result
from app.db.session import session_scope
from app.rubric.irr import per_domain_irr
from app.rubric.workflow import _fetch_ratings
from app.rubric.workflow import compute_result_irr_and_archive as _compute_and_archive
from app.worker import celery_app

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@celery_app.task(name="rubric.compute_result_irr_and_archive")
def compute_result_irr_and_archive(result_id: str) -> None:
    with session_scope() as session:
        _compute_and_archive(session, uuid.UUID(result_id))


def _fetch_archived_results_for_slice(session: Session, slice_definition: dict) -> list[Result]:
    stmt = select(Result).where(Result.queue_state == "archived")
    if "provenance" in slice_definition:
        stmt = stmt.where(Result.provenance == slice_definition["provenance"])
    if "expected_outcome" in slice_definition:
        stmt = stmt.where(Result.expected_outcome == slice_definition["expected_outcome"])
    return list(session.execute(stmt).scalars().all())


def _run_compute_slice_irr(session: Session, slice_definition: dict) -> IRRBatch:
    """Corpus/slice-level IRR (ARCH §14.4, the evidentiary statistic) over
    every archived result matching `slice_definition` (e.g.
    `{"provenance": "clinician_submitted"}`). PRD-046: never pools
    `auto_generated` + `clinician_submitted` unless the caller's own
    `slice_definition` explicitly asks for both."""
    results = _fetch_archived_results_for_slice(session, slice_definition)
    by_domain: dict[str, list[list[int | None]]] = {}
    for result in results:
        ratings = _fetch_ratings(session, result.id)
        per_result_domain: dict[str, dict[uuid.UUID, int]] = {}
        for r in ratings:
            per_result_domain.setdefault(r.domain_code, {})[r.rater_id] = r.score
        rater_ids = sorted({r.rater_id for r in ratings}, key=str)
        for domain, scores in per_result_domain.items():
            by_domain.setdefault(domain, []).append([scores.get(rid) for rid in rater_ids])

    irr_results = per_domain_irr(by_domain) if by_domain else []
    batch = IRRBatch(
        slice_definition=slice_definition,
        per_domain={r.domain_code: r.value for r in irr_results},
        secondary={},
        n_items=len(results),
        n_raters=max((r.n_raters for r in irr_results), default=0),
        config_snapshot={},
    )
    session.add(batch)
    return batch


@celery_app.task(name="rubric.compute_slice_irr")
def compute_slice_irr(slice_definition: dict) -> None:
    with session_scope() as session:
        _run_compute_slice_irr(session, slice_definition)
