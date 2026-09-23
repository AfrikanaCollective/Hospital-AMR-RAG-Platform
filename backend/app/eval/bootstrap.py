"""Shared bootstrap-CI helpers (PRD-112 / ARCH-043;
UNIFIED-ABLATION-PROPOSAL.md §3.7, §4 point 3, §13).

`bootstrap_ci` is `app.eval.model_ablation.ablation._bootstrap_ci`,
promoted here unchanged (same math, same defaults) so it has one home
instead of a private per-module copy — `model_ablation.ablation` now
imports it from here rather than defining its own (DEVIATIONS.md #192).

`paired_bootstrap_ci_delta` is a percentile-bootstrap CI on the
*difference* between two conditions' per-query scores, resampling the
SAME query indices each draw for both arms. This is the correct method
when `scores_a[i]`/`scores_b[i]` are the same query under two different
ablation conditions (Level 1/2/3 comparisons are always paired this way —
UNIFIED-ABLATION-PROPOSAL.md §3.7, "avoid treating the configurations as
independent samples"). Resampling `scores_a` and `scores_b` independently
would ignore the correlation between paired conditions and overstate the
delta's true uncertainty.

`paired_bootstrap_test` (DEVIATIONS.md #202, operator request 2026-09-23:
"Δ Recall@K (95% CI Interval), p-value") is the same paired resampling,
also returning a two-sided bootstrap p-value on `mean(scores_a) ==
mean(scores_b)`, computed from the SAME resampled delta distribution as
the CI — one bootstrap pass, not a second independent one. Both functions
share `_paired_bootstrap_deltas` so neither duplicates the resampling
logic.
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


def _validate_paired(scores_a: list[float], scores_b: list[float]) -> None:
    if len(scores_a) != len(scores_b):
        raise ValueError(
            "paired bootstrap requires equal-length, index-aligned score arrays "
            f"(got {len(scores_a)} and {len(scores_b)})"
        )


def _paired_bootstrap_deltas(
    a: np.ndarray, b: np.ndarray, *, rng: np.random.Generator, n_resamples: int
) -> np.ndarray:
    """One resample draw = one set of query indices (with replacement),
    reused for BOTH arms — preserves the natural pairing between a query's
    two scores through the resample, not just in the point estimate."""
    n = len(a)
    idx = rng.integers(0, n, size=(n_resamples, n))
    return a[idx].mean(axis=1) - b[idx].mean(axis=1)


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
    comparing mismatched queries)."""
    _validate_paired(scores_a, scores_b)
    if not scores_a:
        return 0.0, 0.0
    a = np.asarray(scores_a, dtype=np.float64)
    b = np.asarray(scores_b, dtype=np.float64)
    deltas = _paired_bootstrap_deltas(a, b, rng=rng, n_resamples=n_resamples)
    lo_pct = (1 - ci) / 2 * 100
    hi_pct = 100 - lo_pct
    return float(np.percentile(deltas, lo_pct)), float(np.percentile(deltas, hi_pct))


def paired_bootstrap_test(
    scores_a: list[float],
    scores_b: list[float],
    *,
    rng: np.random.Generator,
    n_resamples: int = DEFAULT_BOOTSTRAP_N,
    ci: float = DEFAULT_BOOTSTRAP_CI,
) -> tuple[float, float, float]:
    """Like `paired_bootstrap_ci_delta`, plus a two-sided bootstrap p-value
    for the null hypothesis `mean(scores_a) == mean(scores_b)`
    (DEVIATIONS.md #202) — computed from the SAME resampled delta
    distribution as the CI, not a second independent resample. Standard
    percentile-bootstrap p-value: the empirical fraction of resampled
    deltas that fall on the opposite side of zero from the OBSERVED point
    estimate, doubled (two-sided), capped at 1.0. Returns `(ci_low,
    ci_high, p_value)`; `p_value=1.0` when there are no paired queries at
    all (nothing to test)."""
    _validate_paired(scores_a, scores_b)
    if not scores_a:
        return 0.0, 0.0, 1.0
    a = np.asarray(scores_a, dtype=np.float64)
    b = np.asarray(scores_b, dtype=np.float64)
    deltas = _paired_bootstrap_deltas(a, b, rng=rng, n_resamples=n_resamples)
    lo_pct = (1 - ci) / 2 * 100
    hi_pct = 100 - lo_pct
    ci_low, ci_high = float(np.percentile(deltas, lo_pct)), float(np.percentile(deltas, hi_pct))
    observed = float(a.mean() - b.mean())
    p_value = 2 * float(np.mean(deltas <= 0)) if observed >= 0 else 2 * float(np.mean(deltas >= 0))
    return ci_low, ci_high, min(1.0, p_value)
