"""Inter-rater reliability (ARCH-021; PRD-044)."""

from __future__ import annotations

import pytest

from app.rubric.irr import krippendorff_alpha_ordinal, per_domain_irr


def test_perfect_agreement_is_alpha_one() -> None:
    assert krippendorff_alpha_ordinal([[5, 5, 5], [4, 4, 4], [3, 3, 3]]) == pytest.approx(1.0)


def test_disagreement_lowers_alpha() -> None:
    value = krippendorff_alpha_ordinal([[5, 4, 5], [1, 5, 1], [3, 3, 2]])
    assert value < 1.0


def test_missing_data_tolerant() -> None:
    value = krippendorff_alpha_ordinal([[5, None, 5], [4, 4, None], [3, 3, 3]])
    assert value == pytest.approx(1.0)


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        krippendorff_alpha_ordinal([])


def test_unanimous_single_item_returns_perfect_agreement_not_a_crash() -> None:
    # Real-Postgres finding (DEVIATIONS.md #81): 3 raters all giving the same
    # score for the same (single-item, per-result) domain has zero variance,
    # which the reference krippendorff package treats as mathematically
    # undefined and raises on — must degrade to 1.0, not crash the archive.
    assert krippendorff_alpha_ordinal([[4, 4, 4]]) == 1.0


def test_all_missing_returns_zero_not_a_crash() -> None:
    assert krippendorff_alpha_ordinal([[None, None]]) == 0.0


def test_per_domain_irr_reports_n_raters_and_n_items() -> None:
    results = per_domain_irr(
        {
            "medical_consensus_alignment": [[5, 5, 5], [4, 4, 3]],
            "extent_of_harm": [[5, 4], [5, 5]],
        },
    )
    by_domain = {r.domain_code: r for r in results}
    assert by_domain["medical_consensus_alignment"].n_raters == 3
    assert by_domain["medical_consensus_alignment"].n_items == 2
    assert by_domain["extent_of_harm"].n_raters == 2
    assert all(r.metric == "krippendorff_alpha_ordinal" for r in results)
