"""Pure aggregation over `PerQueryResult` rows into the three statistical
comparisons requirement XII asks for (UNIFIED-ABLATION-PROPOSAL.md §3.7,
§4 points 4/5): Level 1 (present-only vs. all-assessed), Level 2 (enriched
vs. raw, within each Level 1), Level 3 (each dense-bearing arm vs. `bm25`,
within each Level 1 x Level 2). No I/O — offline-testable on a plain list
of `PerQueryResult`, mirroring every other pure-compute layer already in
this codebase (CLAUDE.md §5).

Pooling convention (proposal §4 point 4, extended consistently to every
comparison here — a judgment call, flagged): a comparison names the
condition(s) it varies; every OTHER free dimension (the remaining
level/alpha) is marginalized by averaging a query's `reciprocal_rank_at_k`
across it first, so each query contributes exactly one scalar score per
side of the comparison — never 16+ separate headline numbers, and never a
query silently overrepresented because it happened to fire on more rows.
`k` is always fixed to one caller-supplied value (typically
`app.eval.ablation_config.mrr_k()`), never pooled across k.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.eval.ablation_config import Level1Condition, Level2Condition, Level3Condition
from app.eval.bootstrap import DEFAULT_BOOTSTRAP_SEED, bootstrap_ci, paired_bootstrap_ci_delta
from app.eval.unified_ablation.per_query import PerQueryResult

BM25_REFERENCE: Level3Condition = "bm25"


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
    level1: Level1Condition | None = None,
    level2: Level2Condition | None = None,
    level3: Level3Condition | None = None,
) -> dict[str, float]:
    """One score per `query_id`: the mean `reciprocal_rank_at_k` over every
    row at this `k` matching the given filters — `None` leaves that
    dimension free (pooled/marginalized), a value pins it."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.k != k:
            continue
        if level1 is not None and row.level1_condition != level1:
            continue
        if level2 is not None and row.level2_condition != level2:
            continue
        if level3 is not None and row.level3_condition != level3:
            continue
        buckets[row.query_id].append(row.reciprocal_rank_at_k)
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
    rows: list[PerQueryResult], *, k: int, seed: int = DEFAULT_BOOTSTRAP_SEED
) -> Level1Summary:
    """Present-only vs. all-assessed, pooled over Level 2 x Level 3 x alpha
    (proposal §3.7 item 1, §4 point 4)."""
    rng = np.random.default_rng(seed)
    present = per_query_scores(rows, k=k, level1="present_only")
    assessed = per_query_scores(rows, k=k, level1="all_assessed")
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
    rows: list[PerQueryResult], *, k: int, seed: int = DEFAULT_BOOTSTRAP_SEED
) -> dict[Level1Condition, Level2Summary]:
    """Enriched vs. raw, WITHIN each Level 1 condition (proposal §3.7 item
    2), pooled over Level 3 x alpha."""
    rng = np.random.default_rng(seed)
    out: dict[Level1Condition, Level2Summary] = {}
    for level1 in ("present_only", "all_assessed"):
        raw = per_query_scores(rows, k=k, level1=level1, level2="raw")
        enriched = per_query_scores(rows, k=k, level1=level1, level2="enriched")
        out[level1] = Level2Summary(
            level1=level1,
            raw=_arm_score(f"{level1}/raw", raw, rng=rng),
            enriched=_arm_score(f"{level1}/enriched", enriched, rng=rng),
            delta=_delta_score(f"{level1}/enriched", f"{level1}/raw", enriched, raw, rng=rng),
        )
    return out


@dataclass(frozen=True)
class Level3Summary:
    level1: Level1Condition
    level2: Level2Condition
    level3: Level3Condition
    reference: ArmScore  # bm25, same L1 x L2 slice
    arm: ArmScore  # the dense-bearing arm, pooled over its own alpha sweep
    delta: DeltaScore  # arm - reference


def summarize_level3(
    rows: list[PerQueryResult], *, k: int, seed: int = DEFAULT_BOOTSTRAP_SEED
) -> list[Level3Summary]:
    """Each dense-bearing arm vs. `bm25`, WITHIN each Level 1 x Level 2
    slice (proposal §3.7 item 3) — 3 dense arms x 2 L1 x 2 L2 = 12
    comparisons, not all-pairwise (proposal §4 point 5). Each arm's own
    alpha sweep is pooled into one score per query, extending point 4's
    pooling principle to alpha — a judgment call, flagged (DEVIATIONS.md
    #192): the full per-alpha detail survives in `per_query_results.jsonl`
    for anyone who wants to slice further."""
    rng = np.random.default_rng(seed)
    out: list[Level3Summary] = []
    for level1 in ("present_only", "all_assessed"):
        for level2 in ("raw", "enriched"):
            reference = per_query_scores(
                rows, k=k, level1=level1, level2=level2, level3=BM25_REFERENCE
            )
            for level3 in ("bm25_sapbert", "bm25_medcpt", "bm25_sapbert_medcpt"):
                arm = per_query_scores(rows, k=k, level1=level1, level2=level2, level3=level3)
                out.append(
                    Level3Summary(
                        level1=level1,
                        level2=level2,
                        level3=level3,
                        reference=_arm_score(
                            f"{level1}/{level2}/{BM25_REFERENCE}", reference, rng=rng
                        ),
                        arm=_arm_score(f"{level1}/{level2}/{level3}", arm, rng=rng),
                        delta=_delta_score(
                            f"{level1}/{level2}/{level3}",
                            f"{level1}/{level2}/{BM25_REFERENCE}",
                            arm,
                            reference,
                            rng=rng,
                        ),
                    )
                )
    return out
