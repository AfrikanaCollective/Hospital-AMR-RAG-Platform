"""Inter-rater reliability (ARCH-021; PRD-044).

Primary metric: Krippendorff's alpha with the ordinal difference function,
computed PER rubric domain. Secondary (descriptive only): Gwet's AC2 and
ICC(2,k).

Rationale (see ARCHITECTURE.md §14.4): any number of raters, variable raters
per item, ordinal 5-point data, missing-data tolerant, chance-corrected.

- Per-result alpha (n_items = 1): indicative only; always reported with
  n_raters / n_items.
- Per-slice / corpus-level alpha: the evidentiary statistic. NEVER pools
  auto_generated + clinician_submitted by default (PRD-046) — the caller
  passes an explicit slice filter.

Phase 3 implements using the `krippendorff` package. This module fixes the
interface so callers and tests are stable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainIRR:
    domain_code: str | None  # None = aggregate
    metric: str
    value: float
    n_raters: int
    n_items: int


def krippendorff_alpha_ordinal(ratings_by_item: list[list[int | None]]) -> float:
    """`ratings_by_item[i]` = one item's scores across raters (None = missing)."""
    raise NotImplementedError("Phase 3: krippendorff.alpha(..., level_of_measurement='ordinal')")


def per_domain_irr(
    domain_ratings: dict[str, list[list[int | None]]],
    *,
    metric: str = "krippendorff_alpha_ordinal",
) -> list[DomainIRR]:
    raise NotImplementedError("Phase 3: compute per-domain IRR + secondary stats (ARCH §14.4)")
