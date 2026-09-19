"""Report-level collapse of `criteria_reuse` into `single_stage` when the
two arms are proven identical (DEVIATIONS.md #159, operator instruction)."""

from __future__ import annotations

from app.eval.orchestration_ablation.ablation import (
    CRITERIA_REUSE,
    SINGLE_STAGE,
    VOCABULARY,
    SliceReport,
)
from app.eval.orchestration_ablation.report import _criteria_reuse_is_redundant, _display_arms


def _report(
    *, arms_present: tuple[str, ...], recall_rows: list[dict], mrr_rows: list[dict]
) -> SliceReport:
    return SliceReport(
        slice_name="well_supported",
        n_questions=10,
        arms_present=arms_present,
        recall_rows=recall_rows,
        mrr_rows=mrr_rows,
        fired_rate={},
        avg_retrieval_calls={},
    )


_IDENTICAL_REPORT = _report(
    arms_present=(SINGLE_STAGE, CRITERIA_REUSE, VOCABULARY),
    recall_rows=[
        {"arm": SINGLE_STAGE, "k": 8, "recall": 0.7},
        {"arm": CRITERIA_REUSE, "k": 8, "recall": 0.7},
        {"arm": VOCABULARY, "k": 8, "recall": 0.6},
    ],
    mrr_rows=[
        {"arm": SINGLE_STAGE, "mrr": 0.1},
        {"arm": CRITERIA_REUSE, "mrr": 0.1},
        {"arm": VOCABULARY, "mrr": 0.12},
    ],
)

_DIVERGENT_RECALL_REPORT = _report(
    arms_present=(SINGLE_STAGE, CRITERIA_REUSE),
    recall_rows=[
        {"arm": SINGLE_STAGE, "k": 8, "recall": 0.7},
        {"arm": CRITERIA_REUSE, "k": 8, "recall": 0.75},  # a real corpus now has criteria chunks
    ],
    mrr_rows=[
        {"arm": SINGLE_STAGE, "mrr": 0.1},
        {"arm": CRITERIA_REUSE, "mrr": 0.1},
    ],
)

_DIVERGENT_MRR_REPORT = _report(
    arms_present=(SINGLE_STAGE, CRITERIA_REUSE),
    recall_rows=[
        {"arm": SINGLE_STAGE, "k": 8, "recall": 0.7},
        {"arm": CRITERIA_REUSE, "k": 8, "recall": 0.7},
    ],
    mrr_rows=[
        {"arm": SINGLE_STAGE, "mrr": 0.1},
        {"arm": CRITERIA_REUSE, "mrr": 0.15},
    ],
)

_NO_CRITERIA_REUSE_REPORT = _report(
    arms_present=(SINGLE_STAGE, VOCABULARY),
    recall_rows=[{"arm": SINGLE_STAGE, "k": 8, "recall": 0.7}],
    mrr_rows=[{"arm": SINGLE_STAGE, "mrr": 0.1}],
)


def test_redundant_when_recall_and_mrr_exactly_match() -> None:
    assert _criteria_reuse_is_redundant([_IDENTICAL_REPORT]) is True


def test_not_redundant_when_recall_diverges() -> None:
    assert _criteria_reuse_is_redundant([_DIVERGENT_RECALL_REPORT]) is False


def test_not_redundant_when_mrr_diverges() -> None:
    assert _criteria_reuse_is_redundant([_DIVERGENT_MRR_REPORT]) is False


def test_redundant_across_multiple_slices_requires_all_to_match() -> None:
    assert _criteria_reuse_is_redundant([_IDENTICAL_REPORT, _DIVERGENT_RECALL_REPORT]) is False
    assert _criteria_reuse_is_redundant([_IDENTICAL_REPORT, _IDENTICAL_REPORT]) is True


def test_vacuously_redundant_when_criteria_reuse_absent() -> None:
    """No `criteria_reuse` in this slice at all (e.g. vocabulary wasn't
    attested when it ran) -- nothing to prove non-redundant, so it's not
    treated as a divergence."""
    assert _criteria_reuse_is_redundant([_NO_CRITERIA_REUSE_REPORT]) is True


def test_display_arms_drops_criteria_reuse_when_redundant() -> None:
    assert _display_arms([_IDENTICAL_REPORT]) == (SINGLE_STAGE, VOCABULARY)


def test_display_arms_keeps_criteria_reuse_when_it_diverges() -> None:
    assert _display_arms([_DIVERGENT_RECALL_REPORT]) == (SINGLE_STAGE, CRITERIA_REUSE)


def test_display_arms_empty_reports_list() -> None:
    assert _display_arms([]) == ()
