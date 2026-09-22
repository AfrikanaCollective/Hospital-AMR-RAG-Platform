"""Seaborn PNG chart generation for the unified hierarchical ablation
report (PRD-112 / ARCH-043; UNIFIED-ABLATION-PROPOSAL.md §5). Requires the
`retrieval-tuning` optional extra (seaborn/pandas/matplotlib); not a core
runtime dependency.

Palette: copied (not imported — same convention as `model_ablation.report`'s
own docstring explains) from `retrieval_tuning.report`'s already
dataviz-skill-validated palette: same surface/ink/gridline/baseline colors,
same 6-slot categorical order. Three panels, one per level, matching the
established A/B/C combined-figure layout (`retrieval_tuning.report`,
`model_ablation.report`):

- Panel A (Level 1): present-only vs. all-assessed clinical signs — two
  categorical points with a bootstrap-CI error bar, plus the paired
  delta CI printed as an annotation (the headline number requirement XII
  asks for, not just a visual comparison).
- Panel B (Level 2): enriched vs. raw query, dodged within each Level 1
  condition — 4 points (2 L1 x 2 L2), color = L2 (raw/enriched, a genuine
  categorical identity), x-position groups by L1.
- Panel C (Level 3): each dense-bearing arm vs. the `bm25` reference,
  faceted along x by Level 1 x Level 2 (4 slices), color = arm — 12 points
  total (3 arms x 4 slices) plus each slice's own `bm25` reference marker.

All three read pre-computed `summary.Level*Summary` objects (this module
does no aggregation itself — mirrors `model_ablation.report` reading
`AblationResult.mrr_rows`' pre-computed `ci_low`/`ci_high` rather than
calling bootstrap machinery from inside a chart function).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from app.eval.ablation_config import Level1Condition
from app.eval.unified_ablation.summary import ArmScore, Level1Summary, Level2Summary, Level3Summary

_SURFACE = "#fcfcfb"
_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE_GRAY = "#c3c2b7"
_CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

_DPI = 300
_FIGSIZE = (9.5, 13.5)
_Y_TOP = 1.0

_LEVEL1_LABELS = {"present_only": "Present-only signs", "all_assessed": "All assessed signs"}
_LEVEL2_LABELS = {"raw": "Raw query", "enriched": "Vocabulary-enriched query"}
_LEVEL3_LABELS = {
    "bm25": "BM25",
    "bm25_sapbert": "BM25 + SapBERT",
    "bm25_medcpt": "BM25 + MedCPT",
    "bm25_sapbert_medcpt": "BM25 + SapBERT + MedCPT",
}
_LEVEL3_ORDER = ("bm25_sapbert", "bm25_medcpt", "bm25_sapbert_medcpt")


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(_SURFACE)
    ax.grid(True, axis="y", color=_GRIDLINE, linewidth=1, linestyle="-")
    ax.grid(False, axis="x")
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
        1.2,
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


def _point_with_ci(ax: plt.Axes, x: float, arm: ArmScore, *, color: str, marker: str = "o") -> None:
    ax.errorbar(
        x,
        arm.mean,
        yerr=[[arm.mean - arm.ci_low], [arm.ci_high - arm.mean]],
        fmt="none",
        ecolor=color,
        elinewidth=1.6,
        capsize=4,
        capthick=1.6,
        zorder=2,
    )
    ax.scatter(
        [x], [arm.mean], s=70, color=color, marker=marker, edgecolor=_SURFACE, linewidth=1, zorder=3
    )


def chart_level1(summary: Level1Summary, k: int, ax: plt.Axes) -> None:
    """Panel A: present-only vs. all-assessed clinical signs, pooled over
    Level 2 x Level 3 x alpha (`summary.summarize_level1`)."""
    _style_axes(ax)
    order = ["present_only", "all_assessed"]
    arms = {"present_only": summary.present_only, "all_assessed": summary.all_assessed}
    for xi, key in enumerate(order):
        _point_with_ci(ax, xi, arms[key], color=_CATEGORICAL[xi])

    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([_LEVEL1_LABELS[k2] for k2 in order], fontsize=9)
    ax.set_xlim(-0.5, len(order) - 0.5)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_ylabel(f"Mean Reciprocal Rank@{k}", fontsize=9)

    d = summary.delta
    ax.text(
        0.5,
        -0.28,
        f"Δ (present-only − all-assessed) = {d.mean_delta:+.3f} "
        f"[{d.ci_low:+.3f}, {d.ci_high:+.3f}], n={d.n}",
        transform=ax.transAxes,
        fontsize=8,
        color=_INK_SECONDARY,
        ha="center",
    )
    _finish(ax, title="Level 1 — clinical-sign query construction (95% bootstrap CI)", letter="A")


def chart_level2(summaries: dict[Level1Condition, Level2Summary], k: int, ax: plt.Axes) -> None:
    """Panel B: enriched vs. raw query, dodged within each Level 1
    condition (`summary.summarize_level2`)."""
    _style_axes(ax)
    l1_order: list[Level1Condition] = ["present_only", "all_assessed"]
    l2_order = ["raw", "enriched"]
    dodge = {"raw": -0.15, "enriched": 0.15}
    colors = {"raw": _CATEGORICAL[0], "enriched": _CATEGORICAL[1]}

    for xi, level1 in enumerate(l1_order):
        l2_summary = summaries[level1]
        arms = {"raw": l2_summary.raw, "enriched": l2_summary.enriched}
        for level2 in l2_order:
            _point_with_ci(ax, xi + dodge[level2], arms[level2], color=colors[level2])

    ax.set_xticks(range(len(l1_order)))
    ax.set_xticklabels([_LEVEL1_LABELS[l1] for l1 in l1_order], fontsize=9)
    ax.set_xlim(-0.5, len(l1_order) - 0.5)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_ylabel(f"Mean Reciprocal Rank@{k}", fontsize=9)

    handles = [
        Line2D([0], [0], marker="o", linestyle="none", markersize=7, color=colors[l2])
        for l2 in l2_order
    ]
    _set_legend(ax, handles, [_LEVEL2_LABELS[l2] for l2 in l2_order])
    _finish(
        ax,
        title="Level 2 — vocabulary/concept enrichment, within each Level 1 (95% bootstrap CI)",
        letter="B",
    )


def chart_level3(summaries: list[Level3Summary], k: int, ax: plt.Axes) -> None:
    """Panel C: each dense-bearing arm vs. `bm25`, faceted along x by
    Level 1 x Level 2 (4 slices), color = arm (`summary.summarize_level3`).
    `bm25`'s own reference point is drawn once per slice, in the fixed
    neutral-gray baseline identity (never one of the three arms' hues)."""
    _style_axes(ax)
    slices = [
        ("present_only", "raw"),
        ("present_only", "enriched"),
        ("all_assessed", "raw"),
        ("all_assessed", "enriched"),
    ]
    dodge = {"bm25_sapbert": -0.2, "bm25_medcpt": 0.0, "bm25_sapbert_medcpt": 0.2}
    colors = dict(zip(_LEVEL3_ORDER, _CATEGORICAL[: len(_LEVEL3_ORDER)], strict=True))

    by_slice: dict[tuple[str, str], dict[str, Level3Summary]] = {}
    for s in summaries:
        by_slice.setdefault((s.level1, s.level2), {})[s.level3] = s

    for xi, key in enumerate(slices):
        rows = by_slice.get(key, {})
        if not rows:
            continue
        reference = next(iter(rows.values())).reference
        _point_with_ci(ax, xi, reference, color=_BASELINE_GRAY, marker="D")
        for level3 in _LEVEL3_ORDER:
            arm_summary = rows.get(level3)
            if arm_summary is None:
                continue
            _point_with_ci(ax, xi + dodge[level3], arm_summary.arm, color=colors[level3])

    ax.set_xticks(range(len(slices)))
    ax.set_xticklabels(
        [f"{_LEVEL1_LABELS[l1]}\n{_LEVEL2_LABELS[l2]}" for l1, l2 in slices], fontsize=7
    )
    ax.set_xlim(-0.5, len(slices) - 0.5)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_ylabel(f"Mean Reciprocal Rank@{k}", fontsize=9)

    handles = [
        Line2D([0], [0], marker="D", linestyle="none", markersize=7, color=_BASELINE_GRAY)
    ] + [
        Line2D([0], [0], marker="o", linestyle="none", markersize=7, color=colors[l3])
        for l3 in _LEVEL3_ORDER
    ]
    labels = [_LEVEL3_LABELS["bm25"]] + [_LEVEL3_LABELS[l3] for l3 in _LEVEL3_ORDER]
    _set_legend(ax, handles, labels)
    _finish(
        ax,
        title=(
            "Level 3 — retrieval/embedding configuration, within each Level 1 x "
            "Level 2 (95% bootstrap CI)"
        ),
        letter="C",
    )


def generate_report(
    level1: Level1Summary,
    level2: dict[Level1Condition, Level2Summary],
    level3: list[Level3Summary],
    *,
    k: int,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "unified_ablation_report.png"

    fig, axes = plt.subplots(3, 1, figsize=_FIGSIZE, dpi=_DPI)
    fig.patch.set_facecolor(_SURFACE)
    fig.subplots_adjust(left=0.11, right=0.72, top=0.95, bottom=0.06, hspace=0.85)

    chart_level1(level1, k, axes[0])
    chart_level2(level2, k, axes[1])
    chart_level3(level3, k, axes[2])

    fig.savefig(out_path, dpi=_DPI, facecolor=_SURFACE)
    plt.close(fig)
    return out_path
