"""Seaborn PNG chart generation for the Phase 6 retrieval-tuning report
(PRD-109 / ARCH-040). Requires the `retrieval-tuning` optional extra
(`pip install -e .[retrieval-tuning]` — seaborn/pandas/matplotlib); not a
core runtime dependency, since nothing on the answer path imports this
module.

Renders as a single combined figure (DEVIATIONS.md #129, follow-up request)
— one 18cm x 21cm, 600dpi PNG with the three charts as stacked panels A/B/C
— rather than three separate PNGs (the original design, PHASE6-PROPOSAL.md
§5). `chart_*` functions draw onto a caller-supplied `Axes` instead of
creating and saving their own `Figure`; `generate_reports` owns the one
`Figure`/`savefig` call.

Palette: light-surface variant of the dataviz skill's palette
(`references/palette.md`), since these are static report images, not a
themeable web page. Chart 1's 11-step BM25 weight (`alpha`) is an ORDERED
dial, not a set of unrelated identities, so it's colored with the
skill's validated sequential blue ramp (magnitude/order -> sequential is the
color-formula's own rule) rather than 11 categorical hues, which both reads
correctly and sidesteps the fixed 8-hue categorical order's CVD-safety limit
at that many series. Chart 2's k-hue was originally only 4 series ({4, 6, 8,
10}) and stayed categorical as a genuine identity encoding; changed per
follow-up request to 11 series ({20, 22, ..., 40}, DEVIATIONS.md #124), then
12 series ({3, 6, ..., 36}, DEVIATIONS.md #125), then 9 series
({4, 8, ..., 36}, DEVIATIONS.md #126) — all past the same 8-hue categorical
CVD-safety ceiling chart 1 already hit — `k` is also an ordered dial
(retrieval depth), so it now reuses the same validated sequential blue ramp
as chart 1's alpha, not a re-derived palette. The RRF
baseline is always a dashed neutral-gray reference line,
never a step of either the ramp or the categorical order, since it isn't
another value of the swept parameter — it's what production actually does
today.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from app.eval.retrieval_tuning.sweep import ALPHA_VALUES, CHART2_K_VALUES, MRR_K, SweepResult

_SURFACE = "#fcfcfb"
_INK_PRIMARY = "#0b0b0b"
_INK_SECONDARY = "#52514e"
_INK_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE_GRAY = "#c3c2b7"
# Fixed categorical order (palette.md slots 1-6); used for chart 2's k-hue
# (only 4 series — a genuine identity encoding, never cycled or reassigned).
_CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
# Sequential blue ramp (palette.md "Sequential hue"), ordinal floor: light end
# is step 250 (#86b6ef, clears the 2:1 ordinal-use contrast floor), dark end
# is step 700 (#0d366b). ALPHA_VALUES is an ORDERED dial (0=pure vector,
# 1=pure BM25), not a set of unrelated identities — 11 values is also past
# where the validated 8-hue categorical order can guarantee CVD-safe
# adjacent-pair separation, so this is both the semantically correct color
# job (magnitude/order -> sequential, per the dataviz skill's color-formula)
# and the only one that scales to this many steps.
_SEQ_LIGHT = "#86b6ef"
_SEQ_DARK = "#0d366b"

_CM_TO_IN = 1 / 2.54
_COMBINED_DPI = 600
_COMBINED_FIGSIZE = (18 * _CM_TO_IN, 21 * _CM_TO_IN)  # 18cm (w) x 21cm (h), per follow-up request
_Y_TOP = 1.0
_Y_DEFAULT_FLOOR = 0.3  # the "well-tuned retrieval" default this project's spec assumed


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    a = tuple(int(c1[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#" + "".join(f"{v:02x}" for v in mixed)


def _sequential_ramp(n: int) -> list[str]:
    if n == 1:
        return [_SEQ_DARK]
    return [_lerp_hex(_SEQ_LIGHT, _SEQ_DARK, i / (n - 1)) for i in range(n)]


def _y_floor(*value_groups: pd.Series) -> float:
    """`0.3` is the right floor when actual performance clears it (the
    common case for a well-tuned system) — but a real, weak-performing
    corpus/question-set combination can genuinely fall below that, and
    silently clipping every point off-chart would render an empty, useless
    plot instead of the true (if disappointing) result. Extends the floor
    down to the real minimum, with a little padding, floored at 0.0; never
    raises it above 0.3."""
    real_min = min(float(v.min()) for v in value_groups if len(v))
    return max(0.0, min(_Y_DEFAULT_FLOOR, real_min - 0.03))


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(_SURFACE)
    ax.grid(True, color=_GRIDLINE, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE_GRAY)
    ax.spines["bottom"].set_color(_BASELINE_GRAY)
    ax.tick_params(colors=_INK_MUTED, labelsize=7)
    ax.xaxis.label.set_color(_INK_SECONDARY)
    ax.yaxis.label.set_color(_INK_SECONDARY)


def _set_legend(
    ax: plt.Axes, handles: list, labels: list[str], *, legend_title: str | None = None
) -> None:
    """Replaces whatever legend seaborn auto-built (if any) with an explicit
    one, placed *outside* the axes to the right — a fixed in-plot corner
    (e.g. "lower right") is only safe when the data is known to stay clear of
    it, which real sweep data does not: recall/MRR curves can occupy any
    region of the chart depending on the actual corpus, so an in-plot legend
    risks sitting directly on top of real lines. `Axes.legend()` called twice
    leaves both artists on screen unless the first is removed first."""
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
        title=legend_title,
        fontsize=7,
        title_fontsize=7,
    )
    legend.get_frame().set_facecolor(_SURFACE)


def _panel_label(ax: plt.Axes, letter: str) -> None:
    """Panel identifier (A/B/C), positioned outside the axes — above and to
    the left of the top-left corner, in the margin reserved between panels
    (see `generate_reports`'s `subplots_adjust`) — rather than inside the
    plot area, so it never sits on top of a data line and needs no backing
    patch."""
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
    ax.set_title(title, color=_INK_PRIMARY, loc="left", fontsize=9, pad=8)
    if ax.get_legend() is None:
        handles, labels = ax.get_legend_handles_labels()
        if labels:
            _set_legend(ax, handles, labels)
    _panel_label(ax, letter)


def chart_k_vs_recall_by_alpha(result: SweepResult, ax: plt.Axes) -> None:
    """Chart 1 (panel A): k (x, 2-60 step 2) vs recall@k (y, floor 0.3 by
    default, extended down if real data is lower), one line per BM25 weight
    alpha (0-1 step 0.1), plus the RRF baseline."""
    df = pd.DataFrame(result.recall_rows)
    _style_axes(ax)

    swept = df[df["alpha"] != "rrf"]
    sns.lineplot(
        data=swept,
        x="k",
        y="recall",
        hue="alpha",
        hue_order=list(ALPHA_VALUES),
        palette=dict(zip(ALPHA_VALUES, _sequential_ramp(len(ALPHA_VALUES)), strict=True)),
        marker="o",
        markersize=4,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.6,
        linewidth=1,
        ax=ax,
    )
    baseline = df[df["alpha"] == "rrf"].sort_values("k")
    ax.plot(
        baseline["k"],
        baseline["recall"],
        # Neutral gray, not a step of the blue sequential ramp — reads as "not
        # one more alpha value" at a glance, consistent with charts 2 and 3.
        color=_BASELINE_GRAY,
        linewidth=1.8,
        linestyle="--",
        marker="D",
        markersize=4,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.8,
        label="RRF (production baseline)",
    )

    k_ticks = sorted({v for v in df["k"].unique() if v % 10 == 0} | {min(df["k"])})
    ax.set_xticks(k_ticks)
    ax.set_ylim(_y_floor(swept["recall"], baseline["recall"]), _Y_TOP)
    ax.set_xlabel("k (chunks retrieved)", fontsize=8)
    ax.set_ylabel("Recall@k (known guideline chunk found)", fontsize=8)
    handles, labels = ax.get_legend_handles_labels()
    _set_legend(
        ax,
        handles,
        [f"alpha={lbl}" if lbl != "RRF (production baseline)" else lbl for lbl in labels],
    )
    _finish(ax, title="Recall@k vs retrieval depth, by BM25 weight", letter="A")


def chart_alpha_vs_recall_by_k(result: SweepResult, ax: plt.Axes) -> None:
    """Chart 2 (panel B): alpha (x, 0-1 step 0.1) vs recall@k (y, floor 0.3
    by default, extended down if real data is lower), one line per k in
    CHART2_K_VALUES (24, 28, ..., 48 — changed per follow-up request,
    DEVIATIONS.md #163; previously 4, 8, ..., 36, #126), plus each k's RRF
    baseline as a matching dotted horizontal reference. 7 series -> colored
    with the same sequential blue ramp as chart 1's alpha, not the
    categorical order (see module docstring)."""
    df = pd.DataFrame(result.chart2_recall_rows)
    focus_k = CHART2_K_VALUES
    _style_axes(ax)
    ramp = _sequential_ramp(len(focus_k))

    swept = df[df["alpha"] != "rrf"].copy()
    swept["k"] = swept["k"].astype(int)
    sns.lineplot(
        data=swept,
        x="alpha",
        y="recall",
        hue="k",
        hue_order=list(focus_k),
        palette=dict(zip(focus_k, ramp, strict=True)),
        marker="o",
        markersize=5,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.8,
        linewidth=1.3,
        ax=ax,
    )
    rrf_focus = df[df["alpha"] == "rrf"]
    for color, k in zip(ramp, focus_k, strict=True):
        rrf_row = rrf_focus[rrf_focus["k"] == k]
        if not rrf_row.empty:
            ax.axhline(
                rrf_row["recall"].iloc[0], color=color, linewidth=0.8, linestyle=":", alpha=0.6
            )

    ax.set_xticks(list(ALPHA_VALUES))
    ax.set_ylim(_y_floor(swept["recall"], rrf_focus["recall"]), _Y_TOP)
    ax.set_xlabel("BM25 weight (alpha); vector weight = 1 - alpha", fontsize=8)
    ax.set_ylabel("Recall@k", fontsize=8)
    handles, labels = ax.get_legend_handles_labels()
    _set_legend(
        ax,
        handles,
        [f"k={lbl}" for lbl in labels],
        legend_title="dotted = RRF at that k",
    )
    _finish(ax, title="Recall@k vs BM25 weight, by retrieval depth", letter="B")


def chart_alpha_vs_mrr(result: SweepResult, ax: plt.Axes) -> None:
    """Chart 3 (panel C): alpha (x, 0-1 step 0.1) vs MRR@k (y, fixed
    0.0-1.0, ticks every 0.1 — 0.0 is MRR's true floor, so unlike charts
    1/2's recall floor no dynamic extension is needed here), plus the RRF
    baseline. `k` = `MRR_K`, whose value has moved on follow-up request more
    than once (settings.top_k=8 originally, #121; the best-recall/deepest-
    chart-2-k derivation, #127; now fixed at 24, #128) — deliberately read
    from the module constant rather than hardcoded here, and the
    title/ylabel below render whatever it currently is."""
    df = pd.DataFrame(result.mrr_rows)
    _style_axes(ax)

    swept = df[df["alpha"] != "rrf"].sort_values("alpha")
    ax.plot(
        swept["alpha"],
        swept["mrr"],
        color=_CATEGORICAL[0],
        linewidth=1.3,
        marker="o",
        markersize=5,
        markeredgecolor=_SURFACE,
        markeredgewidth=0.8,
        label="weighted fusion",
    )
    baseline = df[df["alpha"] == "rrf"]
    if not baseline.empty:
        ax.axhline(
            baseline["mrr"].iloc[0],
            color=_BASELINE_GRAY,
            linewidth=1.3,
            linestyle="--",
            label="RRF (production baseline)",
        )

    ax.set_xticks(list(ALPHA_VALUES))
    ax.set_yticks([round(i / 10, 1) for i in range(11)])
    ax.set_ylim(0.0, _Y_TOP)
    ax.set_xlabel("BM25 weight (alpha); vector weight = 1 - alpha", fontsize=8)
    ax.set_ylabel(f"Mean Reciprocal Rank@{MRR_K}", fontsize=8)
    _finish(ax, title=f"Mean Reciprocal Rank@{MRR_K} vs BM25 weight", letter="C")


def generate_reports(result: SweepResult, out_dir: Path) -> list[Path]:
    """Renders all three charts as stacked panels (A/B/C, top to bottom) in
    one combined figure — 18cm x 21cm at 600dpi, per follow-up request
    (DEVIATIONS.md #129) — rather than three separate PNGs (the original
    design)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="white")
    out_path = out_dir / "retrieval_tuning_report.png"

    fig, axes = plt.subplots(3, 1, figsize=_COMBINED_FIGSIZE, dpi=_COMBINED_DPI)
    fig.patch.set_facecolor(_SURFACE)
    # Fixed margins, not bbox_inches="tight": the figure's physical size is the
    # point of this layout (18cm x 21cm), and "tight" would grow the saved
    # canvas to fit the outside-right legends, silently violating that size.
    fig.subplots_adjust(left=0.12, right=0.74, top=0.93, bottom=0.055, hspace=0.65)

    chart_k_vs_recall_by_alpha(result, axes[0])
    chart_alpha_vs_recall_by_k(result, axes[1])
    chart_alpha_vs_mrr(result, axes[2])

    fig.savefig(out_path, dpi=_COMBINED_DPI, facecolor=_SURFACE)
    plt.close(fig)
    return [out_path]
