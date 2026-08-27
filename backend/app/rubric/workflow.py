"""Multi-rater workflow state machine (ARCH §14.2, §14.3; PRD-042, PRD-043, PRD-047).

UNRATED -> OPEN_QUEUE -> (>= IRR_MIN_RATERS distinct raters) -> compute IRR -> ARCHIVED.
Until the minimum is met the result stays visible in the open queue to any
clinician (except its producer / raters who already rated it).

Phase 3 implements. This module currently defines the states and the guard
predicates so tests and the API can be written against them.
"""

from __future__ import annotations

from enum import StrEnum


class QueueState(StrEnum):
    UNRATED = "unrated"
    OPEN_QUEUE = "open"
    ARCHIVED = "archived"


def is_eligible_rater(*, rater_id: str, result_producer_id: str | None,
                      already_rated_by: set[str]) -> bool:
    """A distinct clinician who did not produce the result and has not rated it."""
    return rater_id != result_producer_id and rater_id not in already_rated_by


def can_archive(*, distinct_rater_count: int, min_raters: int,
                all_domains_scored_by_each: bool) -> bool:
    return distinct_rater_count >= min_raters and all_domains_scored_by_each


def compute_result_irr(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Phase 3: per-result IRR then archive (ARCH §14.4, app.rubric.irr)")
