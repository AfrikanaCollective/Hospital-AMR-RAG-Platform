"""Pure aggregation over `PerQueryResult` rows into the statistical
comparisons requirement XII asks for (UNIFIED-ABLATION-PROPOSAL.md §3.7,
§4 points 4/5, §12): Level 1 (present-only vs. all-assessed), Level 2
(enriched vs. raw, within each Level 1), Level 3 (recall@k as a function
of `bm25_weight`, the continuous BM25/SapBERT weighted-rank-fusion sweep).
No I/O — offline-testable on a plain list of `PerQueryResult`, mirroring
every other pure-compute layer already in this codebase (CLAUDE.md §5).

**Restructured 2026-09-23** (operator request, DEVIATIONS.md #201): the
primary metric is now recall@k (`PerQueryResult.recall_at_k`), not MRR@k
— `per_query_scores`/every `summarize_*` function takes a `metric`
selector (`"recall"` default, `"mrr"` for the still-available secondary
view, reading `reciprocal_rank_at_k`). Level 3's old "each arm vs. `bm25`"
comparison (`summarize_level3`) and the RRF-vs-alpha-blend mechanism
comparison (`summarize_level3_mechanism`, proposal §11) are both removed
— MedCPT and RRF fusion are dropped entirely, and Level 3 is no longer a
set of named arms to compare, it's one continuous curve over
`bm25_weight`. `summarize_level3_curve` replaces both.

Pooling convention (proposal §4 point 4, extended consistently to every
comparison here — a judgment call, flagged): a comparison names the
condition(s) it varies; every OTHER free dimension is marginalized by
averaging a query's metric value across it first, so each query
contributes exactly one scalar score per side of the comparison. `k` is
always fixed to one caller-supplied value (typically
`app.eval.ablation_config.mrr_k()`), never pooled across k.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.eval.ablation_config import Level1Condition, Level2Condition
from app.eval.bootstrap import DEFAULT_BOOTSTRAP_SEED, bootstrap_ci, paired_bootstrap_ci_delta
from app.eval.unified_ablation.per_query import PerQueryResult

Metric = Literal["recall", "mrr"]


def _metric_value(row: PerQueryResult, metric: Metric) -> float:
    return row.recall_at_k if metric == "recall" else row.reciprocal_rank_at_k


@dataclass(frozen=True)
class ArmScore:
    label: str
    n: int
    mean: float
    ci_low: float
    ci_high: float


@dataclass(frozen=True)
class DeltaScore:
    """`mean_delta` = mean(scores_a) - mean(scores_b), over the queries
    common to both (a true paired comparison — a query missing from either
    side contributes to neither)."""

    label_a: str
    label_b: str
    n: int
    mean_delta: float
    ci_low: float
    ci_high: float


def per_query_scores(
    rows: list[PerQueryResult],
    *,
    k: int,
    metric: Metric = "recall",
    level1: Level1Condition | None = None,
    level2: Level2Condition | None = None,
    bm25_weight: float | None = None,
) -> dict[str, float]:
    """One score per `query_id`: the mean of `metric` over every row at
    this `k` matching the given filters — `None` leaves that dimension
    free (pooled/marginalized), a value pins it."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.k != k:
            continue
        if level1 is not None and row.level1_condition != level1:
            continue
        if level2 is not None and row.level2_condition != level2:
            continue
        if bm25_weight is not None and row.bm25_weight != bm25_weight:
            continue
        buckets[row.query_id].append(_metric_value(row, metric))
    return {qid: float(np.mean(scores)) for qid, scores in buckets.items()}


def _arm_score(label: str, scores: dict[str, float], *, rng: np.random.Generator) -> ArmScore:
    values = list(scores.values())
    lo, hi = bootstrap_ci(values, rng=rng)
    mean = float(np.mean(values)) if values else 0.0
    return ArmScore(label=label, n=len(values), mean=mean, ci_low=lo, ci_high=hi)


def _delta_score(
    label_a: str,
    label_b: str,
    scores_a: dict[str, float],
    scores_b: dict[str, float],
    *,
    rng: np.random.Generator,
) -> DeltaScore:
    shared = sorted(set(scores_a) & set(scores_b))
    a = [scores_a[q] for q in shared]
    b = [scores_b[q] for q in shared]
    lo, hi = paired_bootstrap_ci_delta(a, b, rng=rng)
    mean_delta = float(np.mean(a) - np.mean(b)) if shared else 0.0
    return DeltaScore(
        label_a=label_a,
        label_b=label_b,
        n=len(shared),
        mean_delta=mean_delta,
        ci_low=lo,
        ci_high=hi,
    )


@dataclass(frozen=True)
class Level1Summary:
    present_only: ArmScore
    all_assessed: ArmScore
    delta: DeltaScore


def summarize_level1(
    rows: list[PerQueryResult],
    *,
    k: int,
    metric: Metric = "recall",
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> Level1Summary:
    """Present-only vs. all-assessed, pooled over Level 2 x bm25_weight
    (proposal §3.7 item 1, §4 point 4)."""
    rng = np.random.default_rng(seed)
    present = per_query_scores(rows, k=k, metric=metric, level1="present_only")
    assessed = per_query_scores(rows, k=k, metric=metric, level1="all_assessed")
    return Level1Summary(
        present_only=_arm_score("present_only", present, rng=rng),
        all_assessed=_arm_score("all_assessed", assessed, rng=rng),
        delta=_delta_score("present_only", "all_assessed", present, assessed, rng=rng),
    )


@dataclass(frozen=True)
class Level2Summary:
    level1: Level1Condition
    raw: ArmScore
    enriched: ArmScore
    delta: DeltaScore


def summarize_level2(
    rows: list[PerQueryResult],
    *,
    k: int,
    metric: Metric = "recall",
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[Level1Condition, Level2Summary]:
    """Enriched vs. raw, WITHIN each Level 1 condition (proposal §3.7 item
    2), pooled over bm25_weight."""
    rng = np.random.default_rng(seed)
    out: dict[Level1Condition, Level2Summary] = {}
    for level1 in ("present_only", "all_assessed"):
        raw = per_query_scores(rows, k=k, metric=metric, level1=level1, level2="raw")
        enriched = per_query_scores(rows, k=k, metric=metric, level1=level1, level2="enriched")
        out[level1] = Level2Summary(
            level1=level1,
            raw=_arm_score(f"{level1}/raw", raw, rng=rng),
            enriched=_arm_score(f"{level1}/enriched", enriched, rng=rng),
            delta=_delta_score(f"{level1}/enriched", f"{level1}/raw", enriched, raw, rng=rng),
        )
    return out


@dataclass(frozen=True)
class Level3CurvePoint:
    bm25_weight: float
    score: ArmScore


@dataclass(frozen=True)
class Level3Curve:
    """One (Level 1, Level 2) slice's recall@k-vs-bm25_weight curve, plus
    the paired delta between the sweep's two endpoints — `bm25_weight=0.0`
    (pure SapBERT) vs. `bm25_weight=1.0` (pure BM25) — as the headline
    comparison, matching the paired-delta convention every other level in
    this module already uses."""

    level1: Level1Condition
    level2: Level2Condition
    points: list[Level3CurvePoint]  # ordered by bm25_weight, ascending
    endpoints_delta: DeltaScore  # bm25_weight=1.0 (BM25) - bm25_weight=0.0 (SapBERT)


def summarize_level3_curve(
    rows: list[PerQueryResult],
    *,
    k: int,
    weight_values: tuple[float, ...],
    metric: Metric = "recall",
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> list[Level3Curve]:
    """recall@k (or MRR@k) as a function of `bm25_weight`, one curve per
    Level 1 x Level 2 slice (4 total) — the weighted-rank-fusion sweep
    itself, not a fixed set of named arms to compare (DEVIATIONS.md #201).
    `weight_values` is caller-supplied (`app.eval.ablation_config
    .bm25_weight_values()`), never hardcoded."""
    rng = np.random.default_rng(seed)
    out: list[Level3Curve] = []
    for level1 in ("present_only", "all_assessed"):
        for level2 in ("raw", "enriched"):
            points = [
                Level3CurvePoint(
                    bm25_weight=w,
                    score=_arm_score(
                        f"{level1}/{level2}/w={w}",
                        per_query_scores(
                            rows, k=k, metric=metric, level1=level1, level2=level2, bm25_weight=w
                        ),
                        rng=rng,
                    ),
                )
                for w in weight_values
            ]
            sapbert_only = per_query_scores(
                rows, k=k, metric=metric, level1=level1, level2=level2, bm25_weight=0.0
            )
            bm25_only = per_query_scores(
                rows, k=k, metric=metric, level1=level1, level2=level2, bm25_weight=1.0
            )
            out.append(
                Level3Curve(
                    level1=level1,
                    level2=level2,
                    points=points,
                    endpoints_delta=_delta_score(
                        f"{level1}/{level2}/bm25_weight=1.0",
                        f"{level1}/{level2}/bm25_weight=0.0",
                        bm25_only,
                        sapbert_only,
                        rng=rng,
                    ),
                )
            )
    return out
