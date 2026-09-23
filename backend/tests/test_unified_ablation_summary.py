"""Pure aggregation of `PerQueryResult` rows into the Level 1/2/3 paired
comparisons requirement XII asks for (PRD-112; UNIFIED-ABLATION-PROPOSAL.md
§3.7). Restructured 2026-09-23 (DEVIATIONS.md #201): recall@k is the new
primary metric (`metric="recall"` default); Level 3 is a continuous
bm25_weight sweep (`summarize_level3_curve`), not a set of named arms."""

from __future__ import annotations

import pytest

from app.eval.unified_ablation.per_query import PerQueryResult
from app.eval.unified_ablation.summary import (
    per_query_scores,
    summarize_level1,
    summarize_level2,
    summarize_level3_curve,
)

_K = 4
_WEIGHTS = (0.0, 0.5, 1.0)


def _row(
    *,
    query_id: str,
    level1: str,
    level2: str,
    bm25_weight: float,
    recall: float,
    mrr: float | None = None,
) -> PerQueryResult:
    return PerQueryResult(
        query_id=query_id,
        patient_id_or_case_id="rec-1",
        experiment_id="exp-1",
        level1_condition=level1,
        level2_condition=level2,
        level3_condition="bm25_sapbert",
        k=_K,
        bm25_weight=bm25_weight,
        query_text="ignored",
        concept_enriched_query="ignored",
        retrieved_ids=["c1"],
        relevant_ids=["c1"],
        first_relevant_rank=1,
        recall_at_k=recall,
        reciprocal_rank_at_k=mrr if mrr is not None else recall,
    )


def _full_grid_rows(
    query_id: str, *, present_only_recall: float, all_assessed_recall: float
) -> list[PerQueryResult]:
    """One query's full Level1 x Level2 x bm25_weight row set — `present_only_recall`
    used for every present_only row, `all_assessed_recall` for every
    all_assessed row, so pooling never changes the expected mean (every
    pooled-over row carries the same value)."""
    rows = []
    for level1, recall in (
        ("present_only", present_only_recall),
        ("all_assessed", all_assessed_recall),
    ):
        for level2 in ("raw", "enriched"):
            for weight in _WEIGHTS:
                rows.append(
                    _row(
                        query_id=query_id,
                        level1=level1,
                        level2=level2,
                        bm25_weight=weight,
                        recall=recall,
                    )
                )
    return rows


def test_per_query_scores_pools_across_every_unpinned_dimension() -> None:
    rows = [
        _row(query_id="q1", level1="present_only", level2="raw", bm25_weight=1.0, recall=1.0),
        _row(query_id="q1", level1="present_only", level2="enriched", bm25_weight=1.0, recall=0.5),
        _row(query_id="q1", level1="all_assessed", level2="raw", bm25_weight=1.0, recall=0.0),
    ]
    scores = per_query_scores(rows, k=_K, level1="present_only")
    assert scores == {"q1": (1.0 + 0.5) / 2}


def test_per_query_scores_filters_by_k() -> None:
    rows = [
        _row(query_id="q1", level1="present_only", level2="raw", bm25_weight=1.0, recall=1.0),
    ]
    assert per_query_scores(rows, k=999, level1="present_only") == {}


def test_per_query_scores_metric_selector_reads_the_right_field() -> None:
    rows = [
        _row(
            query_id="q1", level1="present_only", level2="raw", bm25_weight=1.0, recall=1.0, mrr=0.3
        ),
    ]
    assert per_query_scores(rows, k=_K, metric="recall", level1="present_only") == {"q1": 1.0}
    assert per_query_scores(rows, k=_K, metric="mrr", level1="present_only") == {"q1": 0.3}


def test_summarize_level1_mean_and_delta_match_the_constant_per_query_values() -> None:
    rows = _full_grid_rows(
        "q1", present_only_recall=0.8, all_assessed_recall=0.2
    ) + _full_grid_rows("q2", present_only_recall=0.6, all_assessed_recall=0.4)
    summary = summarize_level1(rows, k=_K)
    assert summary.present_only.mean == pytest.approx(0.7)  # (0.8 + 0.6) / 2
    assert summary.all_assessed.mean == pytest.approx(0.3)  # (0.2 + 0.4) / 2
    assert summary.present_only.n == 2
    assert summary.delta.mean_delta == pytest.approx(0.7 - 0.3)
    assert summary.delta.n == 2
    assert summary.delta.ci_low <= summary.delta.mean_delta <= summary.delta.ci_high


def test_summarize_level1_zero_delta_when_conditions_are_identical() -> None:
    rows = _full_grid_rows("q1", present_only_recall=0.5, all_assessed_recall=0.5)
    summary = summarize_level1(rows, k=_K)
    assert summary.delta.mean_delta == 0.0
    assert summary.delta.ci_low == 0.0
    assert summary.delta.ci_high == 0.0


def test_summarize_level2_produces_one_entry_per_level1_condition() -> None:
    rows = _full_grid_rows("q1", present_only_recall=0.9, all_assessed_recall=0.1)
    summary = summarize_level2(rows, k=_K)
    assert set(summary) == {"present_only", "all_assessed"}
    assert summary["present_only"].raw.mean == pytest.approx(0.9)
    assert summary["present_only"].enriched.mean == pytest.approx(0.9)
    assert summary["present_only"].delta.mean_delta == pytest.approx(0.0)


def test_summarize_level3_curve_produces_one_curve_per_slice_with_all_weight_points() -> None:
    rows = _full_grid_rows("q1", present_only_recall=0.9, all_assessed_recall=0.1)
    curves = summarize_level3_curve(rows, k=_K, weight_values=_WEIGHTS)
    assert len(curves) == 4  # 2 level1 x 2 level2
    seen = {(c.level1, c.level2) for c in curves}
    assert len(seen) == 4
    for curve in curves:
        assert [p.bm25_weight for p in curve.points] == list(_WEIGHTS)
        # constant-per-query rows -> every weight point has the same mean
        assert all(p.score.mean == pytest.approx(curve.points[0].score.mean) for p in curve.points)
    # constant-per-query rows -> endpoints are equal -> zero delta
    assert all(c.endpoints_delta.mean_delta == pytest.approx(0.0) for c in curves)


def test_summarize_level3_curve_reflects_a_real_weight_dependent_difference() -> None:
    rows = [
        _row(query_id="q1", level1="present_only", level2="raw", bm25_weight=0.0, recall=0.2),
        _row(query_id="q1", level1="present_only", level2="raw", bm25_weight=1.0, recall=0.9),
    ]
    curves = summarize_level3_curve(rows, k=_K, weight_values=(0.0, 1.0))
    matching = next(c for c in curves if c.level1 == "present_only" and c.level2 == "raw")
    by_weight = {p.bm25_weight: p.score.mean for p in matching.points}
    assert by_weight[0.0] == pytest.approx(0.2)
    assert by_weight[1.0] == pytest.approx(0.9)
    assert matching.endpoints_delta.mean_delta == pytest.approx(0.7)  # w=1.0 - w=0.0


def test_summarize_level3_curve_metric_selector_uses_mrr_when_requested() -> None:
    rows = [
        _row(
            query_id="q1",
            level1="present_only",
            level2="raw",
            bm25_weight=1.0,
            recall=1.0,
            mrr=0.25,
        ),
    ]
    curves = summarize_level3_curve(rows, k=_K, weight_values=(1.0,), metric="mrr")
    matching = next(c for c in curves if c.level1 == "present_only" and c.level2 == "raw")
    assert matching.points[0].score.mean == pytest.approx(0.25)
