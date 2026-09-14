"""Inter-rater reliability (ARCH-021; PRD-044).

Primary metric: Krippendorff's alpha with the ordinal difference function,
computed PER rubric domain. Secondary (descriptive only, DEVIATIONS.md #77 —
deferred): Gwet's AC2 and ICC(2,k).

Rationale (see ARCHITECTURE.md §14.4): any number of raters, variable raters
per item, ordinal 5-point data, missing-data tolerant, chance-corrected.

- Per-result alpha (n_items = 1): indicative only; always reported with
  n_raters / n_items.
- Per-slice / corpus-level alpha: the evidentiary statistic. NEVER pools
  auto_generated + clinician_submitted by default (PRD-046) — the caller
  passes an explicit slice filter.

Uses the `krippendorff` package (ARCH-021).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from krippendorff import alpha as _krippendorff_alpha


@dataclass(frozen=True)
class DomainIRR:
    domain_code: str | None  # None = aggregate
    metric: str
    value: float
    n_raters: int
    n_items: int


def krippendorff_alpha_ordinal(ratings_by_item: list[list[int | None]]) -> float:
    """`ratings_by_item[i]` = one item's scores across raters (None = missing).
    Transposed to raters x items (the `krippendorff` package's expected
    `reliability_data` shape) with `None` -> `NaN`.

    Degenerate case (DEVIATIONS.md #81): when every present rating is
    identical (e.g. all 3 raters score `5` on this domain for this result —
    entirely plausible, especially at n_items=1, the per-result case), there
    is no variance anywhere in the data and Krippendorff's alpha is
    mathematically undefined (the reference `krippendorff` package raises
    `ValueError: There has to be more than one value in the domain`).
    Unanimous agreement is the definitional limit of perfect reliability, so
    this is reported as `1.0` rather than propagating the exception and
    aborting the archival step — a real gap a real-Postgres verification run
    surfaced (offline unit tests only exercised items with some variance)."""
    if not ratings_by_item:
        raise ValueError("no items to compute alpha over")
    present = [score for row in ratings_by_item for score in row if score is not None]
    if len(set(present)) <= 1:
        return 1.0 if present else 0.0
    n_raters = max((len(row) for row in ratings_by_item), default=0)
    matrix = np.full((n_raters, len(ratings_by_item)), np.nan)
    for item_idx, scores in enumerate(ratings_by_item):
        for rater_idx, score in enumerate(scores):
            if score is not None:
                matrix[rater_idx, item_idx] = score
    return float(_krippendorff_alpha(reliability_data=matrix, level_of_measurement="ordinal"))


def per_domain_irr(
    domain_ratings: dict[str, list[list[int | None]]],
    *,
    metric: str = "krippendorff_alpha_ordinal",
) -> list[DomainIRR]:
    """`domain_ratings[domain_code][i]` = item i's scores across raters, for
    that domain. Computed per domain (ARCH §14.4) — never averaged across
    domains into one number, since each domain measures something distinct."""
    results = []
    for domain_code, ratings_by_item in domain_ratings.items():
        n_raters = max((len(row) for row in ratings_by_item), default=0)
        value = krippendorff_alpha_ordinal(ratings_by_item)
        results.append(
            DomainIRR(
                domain_code=domain_code,
                metric=metric,
                value=value,
                n_raters=n_raters,
                n_items=len(ratings_by_item),
            )
        )
    return results
