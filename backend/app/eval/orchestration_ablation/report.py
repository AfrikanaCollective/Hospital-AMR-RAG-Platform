"""Seaborn PNG chart generation for the Phase 7 orchestration-ablation report
(PRD-111; PHASE7-PROPOSAL.md §6). Requires the `retrieval-tuning` optional
extra (seaborn/pandas/matplotlib) — not a core runtime dependency.

Three arms is a genuine categorical identity (not an ordered dial like Phase
6's `alpha`/`k`), so this uses the dataviz skill's validated categorical
palette directly — slots 1-3 (blue/orange/aqua), the only three that clear
every CVD/normal-vision gate under all-pairs comparison, not just adjacent
pairs (`references/palette.md`). Same light-surface report style as
`app.eval.retrieval_tuning.report` for visual consistency across the
project's PNG reports.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.eval.orchestration_ablation.ablation import (
    CRITERIA_REUSE,
    SINGLE_STAGE,
    VOCABULARY,
    SliceReport,
)

_SURFACE = "#fcfcfb"
_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_GRIDLINE = "#e1e0d9"

_ARM_LABEL = {
    SINGLE_STAGE: "single-stage",
    CRITERIA_REUSE: "criteria-reuse",
    VOCABULARY: "vocabulary",
}
_ARM_COLOR = {
    SINGLE_STAGE: "#2a78d6",  # categorical slot 1 (blue)
    CRITERIA_REUSE: "#eb6834",  # categorical slot 2 (orange)
    VOCABULARY: "#1baf7a",  # categorical slot 3 (aqua)
}


def _recall_map(report: SliceReport, arm: str) -> dict[int, float]:
    return {row["k"]: row["recall"] for row in report.recall_rows if row["arm"] == arm}


def _mrr_value(report: SliceReport, arm: str) -> float | None:
    return next((row["mrr"] for row in report.mrr_rows if row["arm"] == arm), None)


def _criteria_reuse_is_redundant(reports: list[SliceReport]) -> bool:
    """True if `criteria_reuse` produced byte-identical recall@k and MRR to
    `single_stage` in every given slice — i.e. it never actually had
    anything to reuse (on this deployment, DEVIATIONS #152: the corpus has
    zero `criteria`-type chunks, so Arm B can structurally never diverge
    from Arm A here). Checked against the actual numbers each time a report
    is built, never assumed — a future corpus that does have criteria
    chunks would make this `False` again and the arms would be shown
    separately, automatically."""
    for report in reports:
        if CRITERIA_REUSE not in report.arms_present:
            continue
        if _recall_map(report, CRITERIA_REUSE) != _recall_map(report, SINGLE_STAGE):
            return False
        if _mrr_value(report, CRITERIA_REUSE) != _mrr_value(report, SINGLE_STAGE):
            return False
    return True


def _display_arms(reports: list[SliceReport]) -> tuple[str, ...]:
    """`arms_present` (from the first report) with `criteria_reuse` dropped
    — collapsed into `single_stage` — when `_criteria_reuse_is_redundant`
    holds across every given slice (DEVIATIONS #159)."""
    arms_present = reports[0].arms_present if reports else ()
    if _criteria_reuse_is_redundant(reports):
        return tuple(a for a in arms_present if a != CRITERIA_REUSE)
    return arms_present


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(_GRIDLINE)
    ax.tick_params(colors=_INK_SECONDARY, labelsize=8)
    ax.yaxis.grid(True, color=_GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)


def chart_recall_by_k(ax: plt.Axes, report: SliceReport) -> None:
    display_arms = _display_arms([report])
    df = pd.DataFrame(report.recall_rows)
    df = df[df["arm"].isin(display_arms)]
    df["arm_label"] = df["arm"].map(_ARM_LABEL)
    sns.barplot(
        data=df,
        x="k",
        y="recall",
        hue="arm_label",
        hue_order=[_ARM_LABEL[a] for a in display_arms],
        palette=[_ARM_COLOR[a] for a in display_arms],
        ax=ax,
    )
    title = f"Recall@k by arm — {report.slice_name} (n={report.n_questions})"
    if CRITERIA_REUSE not in display_arms and CRITERIA_REUSE in report.arms_present:
        title += "\n(criteria-reuse collapsed into single-stage — identical, DEVIATIONS #152/#159)"
    ax.set_title(title, color=_INK_PRIMARY, fontsize=10)
    ax.set_xlabel("k", color=_INK_SECONDARY, fontsize=9)
    ax.set_ylabel("recall", color=_INK_SECONDARY, fontsize=9)
    ax.set_ylim(0, 1)
    ax.legend(title=None, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    _style_axes(ax)


def chart_mrr(ax: plt.Axes, reports: list[SliceReport]) -> None:
    display_arms = _display_arms(reports)
    rows = []
    for report in reports:
        for row in report.mrr_rows:
            if row["arm"] not in display_arms:
                continue
            rows.append({"slice": report.slice_name, "arm": row["arm"], "mrr": row["mrr"]})
    df = pd.DataFrame(rows)
    df["arm_label"] = df["arm"].map(_ARM_LABEL)
    sns.barplot(
        data=df,
        x="slice",
        y="mrr",
        hue="arm_label",
        hue_order=[_ARM_LABEL[a] for a in display_arms],
        palette=[_ARM_COLOR[a] for a in display_arms],
        ax=ax,
    )
    title = f"MRR@{8} by arm and slice"
    had_criteria_reuse = any(CRITERIA_REUSE in r.arms_present for r in reports)
    if CRITERIA_REUSE not in display_arms and had_criteria_reuse:
        title += "\n(criteria-reuse collapsed into single-stage — identical, DEVIATIONS #152/#159)"
    ax.set_title(title, color=_INK_PRIMARY, fontsize=10)
    ax.set_xlabel("")
    ax.set_ylabel("MRR", color=_INK_SECONDARY, fontsize=9)
    ax.set_ylim(0, 1)
    ax.legend(title=None, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    _style_axes(ax)


def chart_fired_rate(ax: plt.Axes, reports: list[SliceReport]) -> None:
    rows = []
    for report in reports:
        for arm, rate in report.fired_rate.items():
            rows.append({"slice": report.slice_name, "arm": arm, "fired_rate": rate})
    df = pd.DataFrame(rows)
    df["arm_label"] = df["arm"].map(_ARM_LABEL)
    arms = [a for a in (CRITERIA_REUSE, VOCABULARY) if any(r["arm"] == a for r in rows)]
    sns.barplot(
        data=df,
        x="slice",
        y="fired_rate",
        hue="arm_label",
        hue_order=[_ARM_LABEL[a] for a in arms],
        palette=[_ARM_COLOR[a] for a in arms],
        ax=ax,
    )
    ax.set_title("Augmentation-fired rate (Arm A never augments)", color=_INK_PRIMARY, fontsize=10)
    ax.set_xlabel("")
    ax.set_ylabel("fraction of questions", color=_INK_SECONDARY, fontsize=9)
    ax.set_ylim(0, 1)
    ax.legend(title=None, fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    _style_axes(ax)


def generate_report(
    well_supported: SliceReport, missing_info: SliceReport, out_dir: str | Path
) -> Path:
    """One combined figure, three stacked panels (A/B/C), same layout
    convention as `app.eval.retrieval_tuning.report.generate_reports`."""
    out_path = Path(out_dir) / "orchestration_ablation_report.png"
    fig, axes = plt.subplots(3, 1, figsize=(18 / 2.54, 21 / 2.54), facecolor=_SURFACE)
    chart_recall_by_k(axes[0], well_supported)
    chart_mrr(axes[1], [well_supported, missing_info])
    chart_fired_rate(axes[2], [well_supported, missing_info])
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=600, facecolor=_SURFACE)
    plt.close(fig)
    return out_path
