"""Seaborn PNG chart generation for the unified hierarchical ablation
report (PRD-112 / ARCH-043; UNIFIED-ABLATION-PROPOSAL.md §5, §12). Requires
the `retrieval-tuning` optional extra (seaborn/pandas/matplotlib); not a
core runtime dependency.

**Restructured 2026-09-23** (operator request, DEVIATIONS.md #201): back
to a 3-panel A/B/C layout (Panel D, the RRF-vs-alpha-blend mechanism
comparison, is removed — RRF is dropped entirely) and the primary metric
is now recall@k, not MRR@k. Panel C is redesigned from a point-with-CI
comparison into a real line chart — `bm25_weight` on the x-axis, recall@k
on the y-axis, one line per Level-1 x Level-2 slice (4 lines) — since
Level 3 is no longer a set of named arms to compare, it's one continuous
BM25/SapBERT weighted-rank-fusion sweep. This mirrors
`retrieval_tuning.report.chart_alpha_vs_recall_by_k`'s own established
"swept continuous parameter on x, metric on y, one line per categorical
group" pattern rather than inventing a new chart shape.

Palette: copied (not imported — same convention as `model_ablation.report`'s
own docstring explains) from `retrieval_tuning.report`'s already
dataviz-skill-validated palette: same surface/ink/gridline/baseline colors,
same 6-slot categorical order.

- Panel A (Level 1): present-only vs. all-assessed clinical signs — two
  categorical points with a bootstrap-CI error bar, plus the paired
  delta CI printed as an annotation.
- Panel B (Level 2): enriched vs. raw query, dodged within each Level 1
  condition — 4 points (2 L1 x 2 L2), color = L2, x-position groups by L1.
- Panel C (Level 3): recall@k vs. `bm25_weight` (0.0=pure SapBERT,
  1.0=pure BM25), one line per Level-1 x Level-2 slice (4 lines, a
  genuine categorical identity, well within the validated 8-hue CVD-safe
  count).

All three read pre-computed `summary.Level*Summary`/`Level3Curve` objects
(this module does no aggregation itself).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from app.eval.ablation_config import Level1Condition, Level2Condition
from app.eval.unified_ablation.summary import ArmScore, Level1Summary, Level2Summary, Level3Curve

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
# Shorter forms for Panel C's combined Level-1/Level-2 legend and endpoint
# annotation, which both need to fit 4 combined labels in a narrow margin —
# the full `_LEVEL1_LABELS`/`_LEVEL2_LABELS` strings ran off the figure
# edge when combined (found live, DEVIATIONS.md #201).
_LEVEL1_SHORT = {"present_only": "Present-only", "all_assessed": "All-assessed"}
_LEVEL2_SHORT = {"raw": "Raw", "enriched": "Enriched"}
_SLICES: tuple[tuple[Level1Condition, Level2Condition], ...] = (
    ("present_only", "raw"),
    ("present_only", "enriched"),
    ("all_assessed", "raw"),
    ("all_assessed", "enriched"),
)
_SLICE_COLORS = dict(zip(_SLICES, _CATEGORICAL[: len(_SLICES)], strict=True))


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
    Level 2 x bm25_weight (`summary.summarize_level1`)."""
    _style_axes(ax)
    order = ["present_only", "all_assessed"]
    arms = {"present_only": summary.present_only, "all_assessed": summary.all_assessed}
    for xi, key in enumerate(order):
        _point_with_ci(ax, xi, arms[key], color=_CATEGORICAL[xi])

    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([_LEVEL1_LABELS[k2] for k2 in order], fontsize=9)
    ax.set_xlim(-0.5, len(order) - 0.5)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_ylabel(f"Recall@{k}", fontsize=9)

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
    ax.set_ylabel(f"Recall@{k}", fontsize=9)

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


def chart_level3(curves: list[Level3Curve], k: int, ax: plt.Axes) -> None:
    """Panel C: recall@k vs. `bm25_weight` (0.0 = pure SapBERT, 1.0 = pure
    BM25), one line per Level-1 x Level-2 slice (`summary
    .summarize_level3_curve`) — Level 3 is a continuous weighted-rank-fusion
    sweep, not a set of named arms (DEVIATIONS.md #201)."""
    _style_axes(ax)

    by_slice = {(c.level1, c.level2): c for c in curves}
    for key in _SLICES:
        curve = by_slice.get(key)
        if curve is None:
            continue
        weights = [p.bm25_weight for p in curve.points]
        means = [p.score.mean for p in curve.points]
        color = _SLICE_COLORS[key]
        ax.plot(
            weights,
            means,
            color=color,
            linewidth=1.6,
            marker="o",
            markersize=5,
            markeredgecolor=_SURFACE,
            markeredgewidth=0.8,
            zorder=3,
        )

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_xlabel(
        "BM25 weight (weighted rank fusion; 0.0 = pure SapBERT, 1.0 = pure BM25)", fontsize=8
    )
    ax.set_ylabel(f"Recall@{k}", fontsize=9)

    handles = [
        Line2D([0], [0], color=_SLICE_COLORS[key], linewidth=1.6, marker="o", markersize=5)
        for key in _SLICES
    ]
    labels = [f"{_LEVEL1_SHORT[l1]} / {_LEVEL2_SHORT[l2]}" for l1, l2 in _SLICES]
    _set_legend(ax, handles, labels)

    lines = []
    for key in _SLICES:
        curve = by_slice.get(key)
        if curve is None:
            continue
        d = curve.endpoints_delta
        l1, l2 = key
        lines.append(
            f"{_LEVEL1_SHORT[l1]}/{_LEVEL2_SHORT[l2]}: Δ(BM25−SapBERT)="
            f"{d.mean_delta:+.3f} [{d.ci_low:+.3f}, {d.ci_high:+.3f}]"
        )
    ax.text(
        0.0,
        -0.30,
        "\n".join(lines),
        transform=ax.transAxes,
        fontsize=6.5,
        color=_INK_SECONDARY,
        ha="left",
        va="top",
    )

    _finish(
        ax,
        title=(
            "Level 3 — BM25/SapBERT weighted-rank fusion sweep, by Level 1 x "
            "Level 2 (95% CI on endpoints)"
        ),
        letter="C",
    )


def generate_report(
    level1: Level1Summary,
    level2: dict[Level1Condition, Level2Summary],
    level3: list[Level3Curve],
    *,
    k: int,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "unified_ablation_report.png"

    fig, axes = plt.subplots(3, 1, figsize=_FIGSIZE, dpi=_DPI)
    fig.patch.set_facecolor(_SURFACE)
    # `right=0.68` (narrower axes than the other panels' own 0.72) and
    # `bottom=0.16` (up from 0.08) -- Panel C's legend (4 combined Level-1/
    # Level-2 labels) and its 4-line endpoint-delta annotation both ran off
    # the figure edge at the tighter margins other panels use fine (found
    # live, DEVIATIONS.md #201).
    fig.subplots_adjust(left=0.11, right=0.68, top=0.95, bottom=0.16, hspace=0.9)

    chart_level1(level1, k, axes[0])
    chart_level2(level2, k, axes[1])
    chart_level3(level3, k, axes[2])

    fig.savefig(out_path, dpi=_DPI, facecolor=_SURFACE)
    plt.close(fig)
    return out_path
