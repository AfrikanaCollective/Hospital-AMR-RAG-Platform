"""Pure aggregation of `PerQueryResult` rows into the Level 1/2/3 paired
comparisons requirement XII asks for (PRD-112; UNIFIED-ABLATION-PROPOSAL.md
§3.7)."""

from __future__ import annotations

import pytest

from app.eval.unified_ablation.per_query import PerQueryResult
from app.eval.unified_ablation.summary import (
    per_query_scores,
    summarize_level1,
    summarize_level2,
    summarize_level3,
)

_K = 4


def _row(
    *,
    query_id: str,
    level1: str,
    level2: str,
    level3: str,
    alpha: float,
    rr: float,
) -> PerQueryResult:
    return PerQueryResult(
        query_id=query_id,
        patient_id_or_case_id="rec-1",
        experiment_id="exp-1",
        level1_condition=level1,
        level2_condition=level2,
        level3_condition=level3,
        k=_K,
        alpha=alpha,
        query_text="ignored",
        concept_enriched_query="ignored",
        retrieved_ids=["c1"],
        relevant_ids=["c1"],
        first_relevant_rank=1,
        reciprocal_rank_at_k=rr,
    )


def _full_grid_rows(
    query_id: str, *, present_only_rr: float, all_assessed_rr: float
) -> list[PerQueryResult]:
    """One query's full 16-arm-equivalent row set (collapsed to 2 alphas x 1
    k for test brevity) — `present_only_rr` used for every present_only row,
    `all_assessed_rr` for every all_assessed row, so pooling never changes
    the expected mean (every pooled-over row carries the same value)."""
    rows = []
    for level1, rr in (("present_only", present_only_rr), ("all_assessed", all_assessed_rr)):
        for level2 in ("raw", "enriched"):
            for level3, alphas in (
                ("bm25", (1.0,)),
                ("bm25_sapbert", (0.0, 1.0)),
                ("bm25_medcpt", (0.0, 1.0)),
                ("bm25_sapbert_medcpt", (0.0, 1.0)),
            ):
                for alpha in alphas:
                    rows.append(
                        _row(
                            query_id=query_id,
                            level1=level1,
                            level2=level2,
                            level3=level3,
                            alpha=alpha,
                            rr=rr,
                        )
                    )
    return rows


def test_per_query_scores_pools_across_every_unpinned_dimension() -> None:
    rows = [
        _row(query_id="q1", level1="present_only", level2="raw", level3="bm25", alpha=1.0, rr=1.0),
        _row(
            query_id="q1",
            level1="present_only",
            level2="enriched",
            level3="bm25",
            alpha=1.0,
            rr=0.5,
        ),
        _row(query_id="q1", level1="all_assessed", level2="raw", level3="bm25", alpha=1.0, rr=0.0),
    ]
    scores = per_query_scores(rows, k=_K, level1="present_only")
    assert scores == {"q1": (1.0 + 0.5) / 2}


def test_per_query_scores_filters_by_k() -> None:
    rows = [
        _row(query_id="q1", level1="present_only", level2="raw", level3="bm25", alpha=1.0, rr=1.0),
    ]
    assert per_query_scores(rows, k=999, level1="present_only") == {}


def test_summarize_level1_mean_and_delta_match_the_constant_per_query_values() -> None:
    rows = _full_grid_rows("q1", present_only_rr=0.8, all_assessed_rr=0.2) + _full_grid_rows(
        "q2", present_only_rr=0.6, all_assessed_rr=0.4
    )
    summary = summarize_level1(rows, k=_K)
    assert summary.present_only.mean == pytest.approx(0.7)  # (0.8 + 0.6) / 2
    assert summary.all_assessed.mean == pytest.approx(0.3)  # (0.2 + 0.4) / 2
    assert summary.present_only.n == 2
    assert summary.delta.mean_delta == pytest.approx(0.7 - 0.3)
    assert summary.delta.n == 2
    assert summary.delta.ci_low <= summary.delta.mean_delta <= summary.delta.ci_high


def test_summarize_level1_zero_delta_when_conditions_are_identical() -> None:
    rows = _full_grid_rows("q1", present_only_rr=0.5, all_assessed_rr=0.5)
    summary = summarize_level1(rows, k=_K)
    assert summary.delta.mean_delta == 0.0
    assert summary.delta.ci_low == 0.0
    assert summary.delta.ci_high == 0.0


def test_summarize_level2_produces_one_entry_per_level1_condition() -> None:
    rows = _full_grid_rows("q1", present_only_rr=0.9, all_assessed_rr=0.1)
    summary = summarize_level2(rows, k=_K)
    assert set(summary) == {"present_only", "all_assessed"}
    assert summary["present_only"].raw.mean == pytest.approx(0.9)
    assert summary["present_only"].enriched.mean == pytest.approx(0.9)
    assert summary["present_only"].delta.mean_delta == pytest.approx(0.0)


def test_summarize_level3_produces_12_comparisons_each_dense_arm_vs_bm25() -> None:
    rows = _full_grid_rows("q1", present_only_rr=0.9, all_assessed_rr=0.1)
    summaries = summarize_level3(rows, k=_K)
    assert len(summaries) == 12  # 3 dense arms x 2 level1 x 2 level2
    seen = {(s.level1, s.level2, s.level3) for s in summaries}
    assert len(seen) == 12
    assert all(s.level3 != "bm25" for s in summaries)
    # constant-per-query rows -> arm and reference means are equal -> zero delta
    assert all(s.delta.mean_delta == pytest.approx(0.0) for s in summaries)


def test_summarize_level3_reflects_a_real_arm_advantage() -> None:
    rows = []
    for level1, level2 in (("present_only", "raw"), ("present_only", "enriched")):
        rows.append(
            _row(query_id="q1", level1=level1, level2=level2, level3="bm25", alpha=1.0, rr=0.2)
        )
        rows.append(
            _row(
                query_id="q1",
                level1=level1,
                level2=level2,
                level3="bm25_sapbert",
                alpha=0.5,
                rr=0.9,
            )
        )
    summaries = summarize_level3(rows, k=_K)
    matching = [s for s in summaries if s.level3 == "bm25_sapbert" and s.level1 == "present_only"]
    assert len(matching) == 2
    for s in matching:
        assert s.arm.mean == 0.9
        assert s.reference.mean == 0.2
        assert s.delta.mean_delta == pytest.approx(0.7)
