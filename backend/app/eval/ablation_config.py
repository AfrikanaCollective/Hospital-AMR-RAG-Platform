"""Explicit configuration representation for the unified hierarchical
ablation (PRD-112 / ARCH-043; UNIFIED-ABLATION-PROPOSAL.md §3.4, §3.6).

One `AblationArm` per leaf configuration in the Level-1 x Level-2 x Level-3
hierarchy (16 total, `ALL_ARMS`) — generated, never hand-enumerated, so the
set of arms can't silently drift out of sync with the three level
definitions. K and alpha are read from `app.config.Settings` (never
hardcoded, per the proposal's own requirement) — shared by this module and
`app.eval.unified_ablation` only; the three pre-existing ablation modules
(`model_ablation`, `retrieval_tuning`, `orchestration_ablation`) keep their
own independent K/alpha/MRR_K constants for now (proposal §8: not silently
migrated in this phase).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from app.config import get_settings

Level1Condition = Literal["present_only", "all_assessed"]
Level2Condition = Literal["enriched", "raw"]
Level3Condition = Literal["bm25", "bm25_sapbert", "bm25_medcpt", "bm25_sapbert_medcpt"]

LEVEL1_CONDITIONS: tuple[Level1Condition, ...] = get_args(Level1Condition)
LEVEL2_CONDITIONS: tuple[Level2Condition, ...] = get_args(Level2Condition)
LEVEL3_CONDITIONS: tuple[Level3Condition, ...] = get_args(Level3Condition)

# The one Level-3 arm with no dense channel to blend against -- never
# alpha-swept; every row for it carries the fixed, mathematically consistent
# alpha=1.0 ("pure BM25", matching `weighted_rank`'s own existing
# convention: alpha=1 -> pure BM25, alpha=0 -> pure dense) rather than a
# null, so every row in the per-query output stays directly comparable on
# `alpha` with no special case downstream (UNIFIED-ABLATION-PROPOSAL.md §3.5).
BM25_ONLY_ALPHA = 1.0


@dataclass(frozen=True)
class AblationArm:
    """One leaf configuration. `experiment_id` per `AblationArm` is
    deliberately NOT part of this dataclass -- an arm is a fixed point in
    the hierarchy's own design space, independent of which run it was
    evaluated in; `experiment_id` belongs to the run (§3.8), not the arm."""

    level1: Level1Condition
    level2: Level2Condition
    level3: Level3Condition

    @property
    def has_alpha_dimension(self) -> bool:
        """False only for `bm25` -- no dense channel, so no alpha sweep."""
        return self.level3 != "bm25"

    @property
    def label(self) -> str:
        """A stable, human-readable identifier for reports/logs -- e.g.
        `"L1-present_only__L2-enriched__L3-bm25_sapbert"`."""
        return f"L1-{self.level1}__L2-{self.level2}__L3-{self.level3}"


ALL_ARMS: tuple[AblationArm, ...] = tuple(
    AblationArm(level1=l1, level2=l2, level3=l3)
    for l1 in LEVEL1_CONDITIONS
    for l2 in LEVEL2_CONDITIONS
    for l3 in LEVEL3_CONDITIONS
)  # 16 = 2 x 2 x 4, generated -- never hand-enumerated (proposal §3.4)


def k_values() -> tuple[int, ...]:
    return get_settings().ablation_k_values_tuple


def alpha_values() -> tuple[float, ...]:
    return get_settings().ablation_alpha_values_tuple


def mrr_k() -> int:
    return get_settings().ablation_mrr_k


def alpha_values_for(arm: AblationArm) -> tuple[float, ...]:
    """The alphas to actually sweep for `arm` -- the full configured grid
    for a dense-bearing arm, or exactly `(BM25_ONLY_ALPHA,)` for `bm25`
    (one row, not `len(ALPHA_VALUES)` identical ones)."""
    if not arm.has_alpha_dimension:
        return (BM25_ONLY_ALPHA,)
    return alpha_values()
