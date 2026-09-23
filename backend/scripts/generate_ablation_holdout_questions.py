"""CLI: python -m scripts.generate_ablation_holdout_questions
[--target-count N] [--dataset-id ID] [--seed N] (PRD-112 / ARCH-043;
DEVIATIONS.md #199; operator request 2026-09-23).

Tops up the ablation-only `eval_question` pool to `--target-count`
(default: `settings.ablation_holdout_target_count`, env
`ABLATION_HOLDOUT_TARGET_COUNT`) via
`app.eval.auto_seed.run_ablation_holdout_generation` — writes ONLY
`EvalQuestion` rows, never a `Result`/review-queue item. A de-identified
record consumed here is excluded from the rubric review queue's own
`run_auto_seed_review_queue` (and vice versa) automatically, via the
shared `EvalQuestion.provenance`+`source_record_id` exclusion check both
pipelines read.

Needs a real Postgres + a real LLM gateway (one real pipeline call per new
question — this is not free or instant) and already-ingested de-identified
records covering at least `--target-count` records. If the configured
dataset doesn't have enough unused records, ingest more first:

    python -m scripts.ingest_deidentified_records \\
      --dataset-dir data/patient_records/deidentified/<dataset> \\
      --attest-deidentified --persist --limit <n>

Long-running at scale: a target in the thousands means thousands of real
gateway calls, likely hours, not minutes. Commits per scenario (same
crash-resilience convention as `run_auto_seed_review_queue`,
DEVIATIONS.md #115) — an interrupted run keeps whatever it already
generated; re-running this script simply resumes the top-up.
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.db.session import session_scope
from app.eval.auto_seed import run_ablation_holdout_generation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ablation-only calibration question generation (PRD-112/ARCH-043)"
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=None,
        help="default: settings.ablation_holdout_target_count",
    )
    parser.add_argument("--dataset-id", type=str, default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    target_count = (
        args.target_count
        if args.target_count is not None
        else settings.ablation_holdout_target_count
    )

    print(
        f"[ablation-holdout] topping up to {target_count} ablation-only question(s) "
        f"(dataset_id={args.dataset_id!r}) -- this may take a long time (one real gateway "
        "call per new question).",
        file=sys.stderr,
    )

    with session_scope() as session:
        created = run_ablation_holdout_generation(
            session,
            target_count=target_count,
            dataset_id=args.dataset_id,
            seed=args.seed,
        )

    print(
        f"[ablation-holdout] created {len(created)} new ablation-only question(s) "
        f"(target {target_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
