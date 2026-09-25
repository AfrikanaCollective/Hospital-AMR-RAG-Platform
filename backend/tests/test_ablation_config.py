"""Explicit configuration representation for the unified hierarchical
ablation (PRD-112 / ARCH-043). Restructured 2026-09-23 (DEVIATIONS.md
#201): Level 3 collapses to a single continuous BM25/SapBERT
weighted-rank-fusion sweep -- MedCPT and RRF are gone."""

from __future__ import annotations

import pytest

from app.eval.ablation_config import (
    ALL_ARMS,
    LEVEL1_CONDITIONS,
    LEVEL2_CONDITIONS,
    LEVEL3_CONDITIONS,
    AblationArm,
    bm25_weight_values,
    k_values,
    mrr_k,
)


def test_all_arms_has_exactly_four_generated_leaf_configurations() -> None:
    """2 (L1) x 2 (L2) x 1 (L3 -- a single weighted-rank-fusion identity,
    swept across `bm25_weight_values()` uniformly, not branched by arm)."""
    assert len(ALL_ARMS) == 4
    assert len(ALL_ARMS) == len(set(ALL_ARMS))  # no duplicates


def test_all_arms_covers_every_combination_of_the_three_levels() -> None:
    seen = {(a.level1, a.level2, a.level3) for a in ALL_ARMS}
    expected = {
        (l1, l2, l3)
        for l1 in LEVEL1_CONDITIONS
        for l2 in LEVEL2_CONDITIONS
        for l3 in LEVEL3_CONDITIONS
    }
    assert seen == expected


def test_arm_label_is_stable_and_human_readable() -> None:
    arm = AblationArm(level1="present_only", level2="enriched", level3="bm25_sapbert")
    assert arm.label == "L1-present_only__L2-enriched__L3-bm25_sapbert"


def test_arm_is_frozen_and_hashable() -> None:
    arm = AblationArm(level1="all_assessed", level2="raw", level3="bm25_sapbert")
    with pytest.raises(AttributeError):
        arm.level1 = "present_only"  # type: ignore[misc]
    assert {arm} == {arm}  # must be hashable to dedupe/set-compare, as the tests above rely on


def test_level3_conditions_has_exactly_one_value() -> None:
    """The single BM25/SapBERT weighted-rank-fusion identity -- `bm25_weight`
    is the swept parameter, not a set of named arm identities."""
    assert set(LEVEL3_CONDITIONS) == {"bm25_sapbert"}


def test_bm25_weight_values_has_six_points_at_0_2_granularity() -> None:
    """w_BM25 in {0.0, 0.2, 0.4, 0.6, 0.8, 1.0} (operator request
    2026-09-25, DEVIATIONS.md #207 / proposal §14) -- down from 11 points
    at 0.1 granularity (#201)."""
    values = bm25_weight_values()
    assert values == pytest.approx((0.0, 0.2, 0.4, 0.6, 0.8, 1.0))


def test_k_values_and_bm25_weight_values_and_mrr_k_are_settings_driven_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ABLATION_K_VALUES", "3,6,9")
    monkeypatch.setenv("ABLATION_BM25_WEIGHT_VALUES", "0.25,0.75")
    monkeypatch.setenv("ABLATION_MRR_K", "5")
    get_settings.cache_clear()
    try:
        assert k_values() == (3, 6, 9)
        assert bm25_weight_values() == (0.25, 0.75)
        assert mrr_k() == 5
    finally:
        get_settings.cache_clear()
