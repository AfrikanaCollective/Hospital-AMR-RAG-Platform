"""Seaborn PNG chart generation for the model-ablation report (PRD-110 /
ARCH-041, PHASE2-EMBEDDING-ABLATION-PROPOSAL.md). Requires the
`retrieval-tuning` optional extra (`pip install -e .[retrieval-tuning]` —
seaborn/pandas/matplotlib, reused rather than duplicated as a separate
extra); not a core runtime dependency.

Palette: intentionally mirrors `app.eval.retrieval_tuning.report`'s
already-dataviz-skill-validated palette (same surface/ink/gridline/baseline
colors, same 6-slot categorical order) rather than re-deriving and
re-validating a new one — copied, not imported, since those are that
module's private constants, not a shared public palette module. The four
things plotted here (`sapbert_bm25`, `medcpt_bm25`, `sapbert_medcpt_bm25`,
`rrf_production`) are genuine categorical identities, not an ordered dial —
unlike `retrieval_tuning.report`'s alpha/k hues — so this stays on the
validated categorical order throughout; 4 series is well within its 8-hue
CVD-safe count, no sequential ramp needed. `rrf_production` (what the
system actually does today) keeps the dashed neutral-gray identity color,
same convention as the Phase 6 charts, never one of the three candidate
arms' categorical hues.

Panel letters sit outside the plot area (above/left of each panel), per the
same layout established for the Phase 6 combined report (DEVIATIONS.md
#130).

Panel B's single-stage/multi-stage split (DEVIATIONS.md #184, follow-up
request): color still encodes the embedding arm (categorical identity,
unchanged from above); marker **shape** now encodes stage (circle =
single-stage, triangle = multi-stage) instead of `rrf_production` getting
its own diamond marker — with two independent visual dimensions in play,
shape had to fully hand over to stage rather than partially carry arm
identity too, so the legend carries two groups (color swatches for arm,
grayscale-marker swatches for stage) rather than one. Falls back to a
single circle marker per arm (previous appearance) when multi-stage wasn't
computed (vocabulary not attested).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D

from app.eval.model_ablation.ablation import (
    ALL_ARMS,
    ARMS,
    MRR_K,
    MULTI_STAGE,
    REFERENCE_ARM,
    SINGLE_STAGE,
    AblationResult,
)

_SURFACE = "#fcfcfb"
_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE_GRAY = "#c3c2b7"
_CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

_ARM_LABELS = {
    "sapbert_bm25": "SapBERT + BM25",
    "medcpt_bm25": "MedCPT + BM25",
    "sapbert_medcpt_bm25": "SapBERT + MedCPT + BM25",
    REFERENCE_ARM: "RRF (production baseline)",
}

_DPI = 300
_FIGSIZE = (9.5, 10.0)
_Y_TOP = 1.0
_Y_DEFAULT_FLOOR = 0.0  # unlike retrieval_tuning's 0.3 assumption, no floor assumption here yet

_STAGE_MARKERS = {SINGLE_STAGE: "o", MULTI_STAGE: "^"}
_STAGE_LABELS = {
    SINGLE_STAGE: "Single-stage (raw question)",
    MULTI_STAGE: "Multi-stage (vocab.-augmented)",
}
_STAGE_DODGE = {SINGLE_STAGE: -0.15, MULTI_STAGE: 0.15}


def _y_floor(*value_groups: pd.Series) -> float:
    real_min = min(float(v.min()) for v in value_groups if len(v))
    return max(0.0, min(_Y_DEFAULT_FLOOR, real_min - 0.03)) if real_min < _Y_DEFAULT_FLOOR else 0.0


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(_SURFACE)
    ax.grid(True, color=_GRIDLINE, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE_GRAY)
    ax.spines["bottom"].set_color(_BASELINE_GRAY)
    ax.tick_params(colors=_INK_MUTED, labelsize=8)
    ax.xaxis.label.set_color(_INK_SECONDARY)
    ax.yaxis.label.set_color(_INK_SECONDARY)


def _set_legend(ax: plt.Axes, handles: list, labels: list[str]) -> None:
    existing = ax.get_legend()
    if existing is not None:
        existing.remove()
    legend = ax.legend(
        handles,
        labels,
        frameon=False,
        labelcolor=_INK_SECONDARY,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        fontsize=8,
    )
    legend.get_frame().set_facecolor(_SURFACE)


def _panel_label(ax: plt.Axes, letter: str) -> None:
    ax.text(
        -0.03,
        1.16,
        letter,
        transform=ax.transAxes,
        fontsize=13,
        fontweight="bold",
        color=_INK_PRIMARY,
        ha="left",
        va="bottom",
    )


def _finish(ax: plt.Axes, *, title: str, letter: str) -> None:
    ax.set_title(title, color=_INK_PRIMARY, loc="left", fontsize=10, pad=8)
    if ax.get_legend() is None:
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            _set_legend(ax, handles, labels)
    _panel_label(ax, letter)


def chart_k_vs_recall_by_arm(result: AblationResult, ax: plt.Axes) -> None:
    """Panel A: k (x, 2-20 step 2 — narrowed from the original 2-60 step 2
    per follow-up request) vs recall@k (y), one line per candidate arm plus
    the fresh production RRF reference."""
    df = pd.DataFrame(result.recall_rows)
    _style_axes(ax)

    swept = df[df["arm"].isin(ARMS)]
    sns.lineplot(
        data=swept,
        x="k",
        y="recall",
        hue="arm",
        hue_order=list(ARMS),
        palette=dict(zip(ARMS, _CATEGORICAL, strict=False)),
        marker="o",
        markersize=5,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.8,
        linewidth=1.3,
        ax=ax,
    )
    baseline = df[df["arm"] == REFERENCE_ARM].sort_values("k")
    ax.plot(
        baseline["k"],
        baseline["recall"],
        color=_BASELINE_GRAY,
        linewidth=1.8,
        linestyle="--",
        marker="D",
        markersize=5,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.8,
        label=REFERENCE_ARM,
    )

    ax.set_xticks(sorted(df["k"].unique()))
    ax.set_ylim(_y_floor(swept["recall"], baseline["recall"]), _Y_TOP)
    ax.set_xlabel("k (chunks retrieved)", fontsize=9)
    ax.set_ylabel("Recall@k (known guideline chunk found)", fontsize=9)
    handles, labels = ax.get_legend_handles_labels()
    _set_legend(ax, handles, [_ARM_LABELS.get(lbl, lbl) for lbl in labels])
    _finish(ax, title="Recall@k by embedding-ablation arm", letter="A")


def chart_mrr_by_arm(result: AblationResult, ax: plt.Axes) -> None:
    """Panel B: MRR@MRR_K (matching retrieval_tuning.sweep's current MRR_K,
    for comparability — 12 as of DEVIATIONS #183, previously 24), one point
    per arm with a 95% bootstrap CI error bar (percentile method over
    per-question scores — `ablation._bootstrap_ci`), per follow-up request
    (was a plain bar with no uncertainty shown, DEVIATIONS.md #132).

    Single-stage vs. multi-stage split (DEVIATIONS.md #184, follow-up
    request): when `result.multi_stage_available`, each arm gets two
    dodged points — color still identifies the embedding arm, marker shape
    now identifies stage (circle = single-stage, triangle = multi-stage;
    Phase 7 Arm C's vocabulary augmentation, `app.eval.orchestration_ablation`)
    — instead of one point per arm. Falls back to the previous single point
    per arm (all circles) when multi-stage wasn't computed for this run
    (vocabulary not attested)."""
    df = pd.DataFrame(result.mrr_rows)
    _style_axes(ax)
    ax.grid(True, axis="y", color=_GRIDLINE, linewidth=1, linestyle="-")
    ax.grid(False, axis="x")

    order = list(ALL_ARMS)
    colors = dict(zip(order, [*_CATEGORICAL[: len(ARMS)], _BASELINE_GRAY], strict=True))
    stages = [SINGLE_STAGE, MULTI_STAGE] if result.multi_stage_available else [SINGLE_STAGE]

    for xi, arm in enumerate(order):
        for stage in stages:
            rows = df[(df["arm"] == arm) & (df["stage"] == stage)]
            if rows.empty:
                continue
            mean = float(rows["mrr"].iloc[0])
            lo, hi = float(rows["ci_low"].iloc[0]), float(rows["ci_high"].iloc[0])
            x = xi + (_STAGE_DODGE[stage] if result.multi_stage_available else 0.0)
            color = colors[arm]
            ax.errorbar(
                x,
                mean,
                yerr=[[mean - lo], [hi - mean]],
                fmt="none",
                ecolor=color,
                elinewidth=1.6,
                capsize=4,
                capthick=1.6,
                zorder=2,
            )
            ax.scatter(
                [x],
                [mean],
                s=64,
                color=color,
                marker=_STAGE_MARKERS[stage],
                edgecolor=_SURFACE,
                linewidth=1,
                zorder=3,
            )

    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([_ARM_LABELS[a] for a in order], rotation=15, ha="right", fontsize=8)
    ax.set_xlim(-0.5, len(order) - 0.5)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_ylabel(f"Mean Reciprocal Rank@{MRR_K}", fontsize=9)

    color_handles = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=7, color=colors[a]) for a in order
    ]
    color_labels = [_ARM_LABELS[a] for a in order]
    if result.multi_stage_available:
        shape_handles = [
            Line2D(
                [0],
                [0],
                marker=_STAGE_MARKERS[s],
                linestyle="none",
                markersize=7,
                color=_INK_SECONDARY,
            )
            for s in (SINGLE_STAGE, MULTI_STAGE)
        ]
        shape_labels = [_STAGE_LABELS[s] for s in (SINGLE_STAGE, MULTI_STAGE)]
        _set_legend(ax, color_handles + shape_handles, color_labels + shape_labels)
        title = (
            f"Mean Reciprocal Rank@{MRR_K} by embedding-ablation arm, "
            "single- vs. multi-stage (95% bootstrap CI)"
        )
    else:
        _set_legend(ax, color_handles, color_labels)
        title = (
            f"Mean Reciprocal Rank@{MRR_K} by embedding-ablation arm (95% bootstrap CI; "
            "multi-stage unavailable — vocabulary not attested)"
        )
    _finish(ax, title=title, letter="B")


def generate_reports(result: AblationResult, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="white")
    out_path = out_dir / "model_ablation_report.png"

    fig, axes = plt.subplots(2, 1, figsize=_FIGSIZE, dpi=_DPI)
    fig.patch.set_facecolor(_SURFACE)
    fig.subplots_adjust(left=0.12, right=0.72, top=0.93, bottom=0.1, hspace=0.75)

    chart_k_vs_recall_by_arm(result, axes[0])
    chart_mrr_by_arm(result, axes[1])

    fig.savefig(out_path, dpi=_DPI, facecolor=_SURFACE)
    plt.close(fig)
    return [out_path]
