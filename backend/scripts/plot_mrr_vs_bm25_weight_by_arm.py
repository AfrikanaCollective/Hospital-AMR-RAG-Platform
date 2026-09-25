"""CLI: python -m scripts.plot_mrr_vs_bm25_weight_by_arm RUN_DIR
[--out FILE] [--k K] [--bm25-weight-values 0.0,0.2,...]
(PRD-112 / ARCH-043 — supplementary figure for a unified ablation run).

Single-panel companion to `scripts/plot_recall_by_bm25_weight.py`: mean
reciprocal rank at one K (MRR@K, the per-query `reciprocal_rank_at_k` —
the ablation's secondary metric) vs. BM25 score weight, one line per
Level-1 x Level-2 arm (Present-only/All-assessed x Raw/Enriched). Output is
an 18 x 18 cm, 300 dpi PNG written next to the input
(`mrr_at_k_vs_bm25_weight_by_arm.png` by default).

K defaults to the ablation's headline k (`app.eval.ablation_config.mrr_k()`,
i.e. `ABLATION_MRR_K`). The weight grid is the configured one (`bm25_weight_values()`). Fails
if K has no rows in the run.

Arms are categorical, so they use four fixed-order categorical hues plus a
distinct marker per arm: two of the hues sit below 3:1 contrast on white, so
identity never rests on color alone.

Purely a read of an existing run's file output — no DB, Qdrant, or model
calls. Requires the `retrieval-tuning` optional extra
(seaborn/pandas/matplotlib).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from app.eval.ablation_config import bm25_weight_values, mrr_k  # noqa: E402
from scripts.plot_recall_by_bm25_weight import (  # noqa: E402
    _CM,
    _DPI,
    _FACET_ORDER,
    _FIGSIZE_CM,
    load_mean_recall,
)

_DEFAULT_OUT_NAME = "mrr_at_k_vs_bm25_weight_by_arm.png"
# Categorical slots 1-4 (blue, orange, aqua, yellow), validated as a set.
_ARM_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
_ARM_MARKERS = ["o", "s", "^", "D"]


def plot(agg: pd.DataFrame, k: int, out_path: Path) -> None:
    agg = agg[agg.k == k]
    weights = sorted(agg.bm25_weight.unique())

    sns.set_theme(style="whitegrid", context="paper")
    g = sns.relplot(
        data=agg,
        x="bm25_weight",
        y="reciprocal_rank_at_k",
        hue="facet",
        hue_order=_FACET_ORDER,
        palette=_ARM_PALETTE,
        style="facet",
        style_order=_FACET_ORDER,
        markers=_ARM_MARKERS,
        dashes=False,
        kind="line",
        markersize=6,
        linewidth=1.5,
    )
    g.figure.set_size_inches(_FIGSIZE_CM * _CM, _FIGSIZE_CM * _CM)
    g.set(xlim=(-0.05, 1.05), ylim=(0, 1), xticks=weights)
    for ax in g.axes.flat:
        ax.set_xticklabels([f"{w:.1f}" for w in weights])
    g.set_axis_labels("BM25 score weight", f"Mean reciprocal rank at k={k}")
    sns.move_legend(
        g,
        "lower center",
        ncol=2,
        title="Level 1 / Level 2 arm",
        bbox_to_anchor=(0.5, 0.0),
        frameon=False,
    )
    g.figure.tight_layout(rect=(0, 0.1, 1, 1))
    g.figure.savefig(out_path, dpi=_DPI)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path, help="results/ablation/<run_id> directory")
    parser.add_argument("--out", type=Path, default=None, help="output PNG path")
    parser.add_argument("--k", type=int, default=None, help="default: ABLATION_MRR_K")
    parser.add_argument(
        "--bm25-weight-values", type=str, default=None, help="comma-separated, e.g. 0.0,0.5,1.0"
    )
    args = parser.parse_args(argv)
    if args.bm25_weight_values is not None:
        os.environ["ABLATION_BM25_WEIGHT_VALUES"] = args.bm25_weight_values

    k = args.k if args.k is not None else mrr_k()
    agg = load_mean_recall(
        args.run_dir / "per_query_results.jsonl",
        bm25_weight_values(),
        metric="reciprocal_rank_at_k",
    )
    if k not in set(agg.k):
        raise SystemExit(f"no rows in {args.run_dir} for k={k}")

    out_path = args.out or args.run_dir / _DEFAULT_OUT_NAME
    plot(agg, k, out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
