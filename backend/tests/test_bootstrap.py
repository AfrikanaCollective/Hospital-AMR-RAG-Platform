"""Shared bootstrap-CI helpers (PRD-112 / ARCH-043; DEVIATIONS.md #192)."""

from __future__ import annotations

import numpy as np
import pytest

from app.eval.bootstrap import bootstrap_ci, paired_bootstrap_ci_delta, paired_bootstrap_test


def test_bootstrap_ci_is_importable_from_its_new_shared_home() -> None:
    """`app.eval.model_ablation.ablation` re-exports this under its old
    private name (DEVIATIONS.md #192) -- this test confirms the real,
    canonical implementation lives here and behaves as expected, not just
    that the re-export exists."""
    rng1 = np.random.default_rng(1234)
    rng2 = np.random.default_rng(1234)
    scores = [0.0, 0.5, 1.0, 0.0, 1.0, 0.5, 0.25]
    assert bootstrap_ci(scores, rng=rng1) == bootstrap_ci(scores, rng=rng2)


def test_bootstrap_ci_empty_scores_is_zero() -> None:
    rng = np.random.default_rng(1234)
    assert bootstrap_ci([], rng=rng) == (0.0, 0.0)


# ── paired_bootstrap_ci_delta ─────────────────────────────────────────────


def test_paired_bootstrap_ci_delta_zero_for_identical_arms() -> None:
    rng = np.random.default_rng(1234)
    scores = [1.0, 0.5, 0.0, 1.0, 0.5]
    lo, hi = paired_bootstrap_ci_delta(scores, scores, rng=rng)
    assert lo == pytest.approx(0.0)
    assert hi == pytest.approx(0.0)


def test_paired_bootstrap_ci_delta_brackets_the_true_mean_difference() -> None:
    rng = np.random.default_rng(1234)
    a = [1.0, 1.0, 0.5, 1.0, 0.5, 1.0, 1.0, 0.5, 1.0, 0.5] * 5  # n=50, mean 0.75
    b = [0.0, 0.5, 0.0, 0.5, 0.0, 0.0, 0.5, 0.0, 0.5, 0.0] * 5  # n=50, mean 0.20
    lo, hi = paired_bootstrap_ci_delta(a, b, rng=rng)
    true_delta = sum(a) / len(a) - sum(b) / len(b)
    assert lo <= true_delta <= hi
    assert lo > 0  # a is unambiguously higher than b here -- CI must exclude 0


def test_paired_bootstrap_ci_delta_mismatched_lengths_raises() -> None:
    rng = np.random.default_rng(1234)
    with pytest.raises(ValueError, match="equal-length"):
        paired_bootstrap_ci_delta([1.0, 0.5], [1.0], rng=rng)


def test_paired_bootstrap_ci_delta_empty_is_zero() -> None:
    rng = np.random.default_rng(1234)
    assert paired_bootstrap_ci_delta([], [], rng=rng) == (0.0, 0.0)


def test_paired_bootstrap_is_narrower_than_naive_independent_resampling_on_correlated_data() -> (
    None
):
    """The whole point of pairing (UNIFIED-ABLATION-PROPOSAL.md §3.7,
    "avoid treating the configurations as independent samples"): when
    scores_a[i]/scores_b[i] are strongly correlated per-query (the same
    query, two conditions, most of the variance is between-query not
    between-condition), the paired delta's CI must be materially narrower
    than what independently resampling each arm and subtracting the two
    CIs' own bounds would suggest -- the independent approach ignores the
    correlation and overstates uncertainty."""
    rng = np.random.default_rng(7)
    n = 60
    # Per-query "difficulty" dominates both arms' scores; condition adds a
    # small, consistent bump -- strong positive correlation between a[i]/b[i].
    base = rng.uniform(0.0, 1.0, size=n)
    a = list(np.clip(base + 0.05, 0.0, 1.0))
    b = list(base)

    paired_lo, paired_hi = paired_bootstrap_ci_delta(a, b, rng=np.random.default_rng(1234))
    paired_width = paired_hi - paired_lo

    # Naive: independently bootstrap each arm's own mean, then take the
    # width of (a's CI) "minus" (b's CI) as if they were independent sums.
    a_lo, a_hi = bootstrap_ci(a, rng=np.random.default_rng(1234))
    b_lo, b_hi = bootstrap_ci(b, rng=np.random.default_rng(1234))
    naive_independent_width = (a_hi - a_lo) + (b_hi - b_lo)

    assert paired_width < naive_independent_width


# ── paired_bootstrap_test ─────────────────────────────────────────────────


def test_paired_bootstrap_test_ci_matches_paired_bootstrap_ci_delta_exactly() -> None:
    """Same resampling logic, same seed -> byte-identical CI to the CI-only
    function (DEVIATIONS.md #202) -- confirms the shared
    `_paired_bootstrap_deltas` helper didn't drift the two apart."""
    a = [1.0, 1.0, 0.5, 1.0, 0.5, 1.0, 1.0, 0.5, 1.0, 0.5] * 5
    b = [0.0, 0.5, 0.0, 0.5, 0.0, 0.0, 0.5, 0.0, 0.5, 0.0] * 5
    ci_lo, ci_hi = paired_bootstrap_ci_delta(a, b, rng=np.random.default_rng(1234))
    test_lo, test_hi, _ = paired_bootstrap_test(a, b, rng=np.random.default_rng(1234))
    assert test_lo == pytest.approx(ci_lo)
    assert test_hi == pytest.approx(ci_hi)


def test_paired_bootstrap_test_p_value_is_tiny_for_an_unambiguous_difference() -> None:
    rng = np.random.default_rng(1234)
    a = [1.0, 1.0, 0.5, 1.0, 0.5, 1.0, 1.0, 0.5, 1.0, 0.5] * 5  # mean 0.75
    b = [0.0, 0.5, 0.0, 0.5, 0.0, 0.0, 0.5, 0.0, 0.5, 0.0] * 5  # mean 0.20
    _, _, p_value = paired_bootstrap_test(a, b, rng=rng)
    assert p_value < 0.01


def test_paired_bootstrap_test_p_value_is_one_for_identical_arms() -> None:
    rng = np.random.default_rng(1234)
    scores = [1.0, 0.5, 0.0, 1.0, 0.5]
    _, _, p_value = paired_bootstrap_test(scores, scores, rng=rng)
    assert p_value == pytest.approx(1.0)


def test_paired_bootstrap_test_mismatched_lengths_raises() -> None:
    rng = np.random.default_rng(1234)
    with pytest.raises(ValueError, match="equal-length"):
        paired_bootstrap_test([1.0, 0.5], [1.0], rng=rng)


def test_paired_bootstrap_test_empty_is_zero_ci_and_p_value_one() -> None:
    rng = np.random.default_rng(1234)
    assert paired_bootstrap_test([], [], rng=rng) == (0.0, 0.0, 1.0)


def test_paired_bootstrap_test_p_value_never_exceeds_one() -> None:
    rng = np.random.default_rng(1234)
    # A near-flat difference should still yield a valid, bounded p-value.
    a = [0.500001, 0.5, 0.500001, 0.5, 0.500001]
    b = [0.5, 0.500001, 0.5, 0.500001, 0.5]
    _, _, p_value = paired_bootstrap_test(a, b, rng=rng)
    assert 0.0 <= p_value <= 1.0
