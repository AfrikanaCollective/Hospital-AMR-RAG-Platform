"""Explicit configuration representation for the unified hierarchical
ablation (PRD-112 / ARCH-043)."""

from __future__ import annotations

import pytest

from app.eval.ablation_config import (
    ALL_ARMS,
    BM25_ONLY_ALPHA,
    LEVEL1_CONDITIONS,
    LEVEL2_CONDITIONS,
    LEVEL3_CONDITIONS,
    AblationArm,
    alpha_values,
    alpha_values_for,
    k_values,
    mrr_k,
)


def test_all_arms_has_exactly_sixteen_generated_leaf_configurations() -> None:
    assert len(ALL_ARMS) == 16
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


def test_only_bm25_lacks_the_alpha_dimension() -> None:
    for arm in ALL_ARMS:
        assert arm.has_alpha_dimension == (arm.level3 != "bm25")


def test_arm_label_is_stable_and_human_readable() -> None:
    arm = AblationArm(level1="present_only", level2="enriched", level3="bm25_sapbert")
    assert arm.label == "L1-present_only__L2-enriched__L3-bm25_sapbert"


def test_arm_is_frozen_and_hashable() -> None:
    arm = AblationArm(level1="all_assessed", level2="raw", level3="bm25")
    with pytest.raises(AttributeError):
        arm.level1 = "present_only"  # type: ignore[misc]
    assert {arm} == {arm}  # must be hashable to dedupe/set-compare, as the tests above rely on


def test_alpha_values_for_bm25_is_exactly_one_fixed_value() -> None:
    bm25_arm = next(a for a in ALL_ARMS if a.level3 == "bm25")
    assert alpha_values_for(bm25_arm) == (BM25_ONLY_ALPHA,)
    assert BM25_ONLY_ALPHA == 1.0  # "pure BM25" per weighted_rank's own convention


def test_alpha_values_for_a_dense_bearing_arm_is_the_full_configured_grid() -> None:
    sapbert_arm = next(a for a in ALL_ARMS if a.level3 == "bm25_sapbert")
    assert alpha_values_for(sapbert_arm) == alpha_values()
    assert len(alpha_values_for(sapbert_arm)) > 1


def test_k_values_and_alpha_values_and_mrr_k_are_settings_driven_not_hardcoded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("ABLATION_K_VALUES", "3,6,9")
    monkeypatch.setenv("ABLATION_ALPHA_VALUES", "0.25,0.75")
    monkeypatch.setenv("ABLATION_MRR_K", "5")
    get_settings.cache_clear()
    try:
        assert k_values() == (3, 6, 9)
        assert alpha_values() == (0.25, 0.75)
        assert mrr_k() == 5
    finally:
        get_settings.cache_clear()
