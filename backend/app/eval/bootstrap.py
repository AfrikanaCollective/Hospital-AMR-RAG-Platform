"""Shared bootstrap-CI helpers (PRD-112 / ARCH-043;
UNIFIED-ABLATION-PROPOSAL.md §3.7, §4 point 3).

`bootstrap_ci` is `app.eval.model_ablation.ablation._bootstrap_ci`,
promoted here unchanged (same math, same defaults) so it has one home
instead of a private per-module copy — `model_ablation.ablation` now
imports it from here rather than defining its own (DEVIATIONS.md #192).

`paired_bootstrap_ci_delta` is new: a percentile-bootstrap CI on the
*difference* between two conditions' per-query scores, resampling the
SAME query indices each draw for both arms. This is the correct method
when `scores_a[i]`/`scores_b[i]` are the same query under two different
ablation conditions (Level 1/2/3 comparisons are always paired this way —
UNIFIED-ABLATION-PROPOSAL.md §3.7, "avoid treating the configurations as
independent samples"). Resampling `scores_a` and `scores_b` independently
would ignore the correlation between paired conditions and overstate the
delta's true uncertainty.
"""

from __future__ import annotations

import numpy as np

# Judgment calls (UNIFIED-ABLATION-PROPOSAL.md §4 point 3): a round resample
# count and an arbitrary but fixed seed, not derived from anything -- reused
# from `model_ablation.ablation`'s own original values for consistency with
# every bootstrap CI already shipped this project.
DEFAULT_BOOTSTRAP_N = 10_000
DEFAULT_BOOTSTRAP_SEED = 1234
DEFAULT_BOOTSTRAP_CI = 0.95


def bootstrap_ci(
    scores: list[float],
    *,
    rng: np.random.Generator,
    n_resamples: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_BOOTSTRAP_CI,
) -> tuple[float, float]:
    """Percentile-bootstrap CI on the mean of `scores`. With very few scores
    (e.g. a 2-question unit-test fixture) this is a wide, not statistically
    meaningful interval — expected, not a bug."""
    if not scores:
        return 0.0, 0.0
    arr = np.asarray(scores, dtype=np.float64)
    resampled = rng.choice(arr, size=(n_resamples, len(arr)), replace=True)
    means = resampled.mean(axis=1)
    lo_pct = (1 - ci) / 2 * 100
    hi_pct = 100 - lo_pct
    return float(np.percentile(means, lo_pct)), float(np.percentile(means, hi_pct))


def paired_bootstrap_ci_delta(
    scores_a: list[float],
    scores_b: list[float],
    *,
    rng: np.random.Generator,
    n_resamples: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_BOOTSTRAP_CI,
) -> tuple[float, float]:
    """Percentile-bootstrap CI on `mean(scores_a) - mean(scores_b)`, paired:
    `scores_a[i]` and `scores_b[i]` must be the same query's score under
    condition A and condition B respectively (same length, index-aligned —
    raises `ValueError` otherwise, fails closed rather than silently
    comparing mismatched queries). Each of the `n_resamples` draws picks one
    set of query indices (with replacement) and reuses it for BOTH arms, so
    the natural pairing between a query's two scores is preserved through
    the resample, not just in the point estimate."""
    if len(scores_a) != len(scores_b):
        raise ValueError(
            "paired bootstrap requires equal-length, index-aligned score arrays "
            f"(got {len(scores_a)} and {len(scores_b)})"
        )
    if not scores_a:
        return 0.0, 0.0
    a = np.asarray(scores_a, dtype=np.float64)
    b = np.asarray(scores_b, dtype=np.float64)
    n = len(a)
    idx = rng.integers(0, n, size=(n_resamples, n))
    deltas = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    lo_pct = (1 - ci) / 2 * 100
    hi_pct = 100 - lo_pct
    return float(np.percentile(deltas, lo_pct)), float(np.percentile(deltas, hi_pct))
