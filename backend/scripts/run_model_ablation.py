"""CLI: python -m scripts.run_model_ablation [--out-dir DIR]
[--concepts-path PATH] (PRD-110 / ARCH-041; Makefile
`make model-ablation-report`).

Runs the offline SapBERT/MedCPT/BM25 ablation against the real Qdrant
guideline collection and the real `eval.eval_question` table (well_supported,
auto_generated, non-empty gold_relevant_chunks — see
`app.eval.retrieval_tuning.sweep.fetch_calibration_questions`), then writes
the PHASE2-EMBEDDING-ABLATION-PROPOSAL.md report PNG.

Needs a real Postgres + Qdrant with an already-ingested guideline corpus and
an already-seeded auto-generated question set — not runnable against
`:memory:`/stub backends, which is what `tests/test_model_ablation.py`
covers instead (CLAUDE.md §5). Requires the `retrieval-tuning` optional
extra (seaborn/pandas/matplotlib) and, for a real (non-stub) run,
`MODEL_ABLATION_BACKEND=local` plus the `local-models` extra
(sentence-transformers/torch, for SapBERT/MedCPT) — the default
`MODEL_ABLATION_BACKEND=stub` produces a report from deterministic fake
embeddings, useful only for exercising this script's plumbing, not for any
real conclusion.

**Panel B's multi-stage point (operator-vocabulary augmentation, Phase 7
Arm C, DEVIATIONS.md #184) requires `data/clinical_concepts.yaml` to be
attested**, same convention as `run_orchestration_ablation.py`. If it isn't,
this script still produces a report with panel B's previous, single-stage-
only appearance and prints why multi-stage was skipped — it never runs
Arm C's augmentation against a placeholder.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.eval.model_ablation.ablation import run_full_ablation
from app.eval.model_ablation.report import generate_reports
from app.retrieval.vectorstore import QdrantVectorStore

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "app/eval/model_ablation/reports"
_DEFAULT_CONCEPTS_PATH = Path(
    os.environ.get("CLINICAL_CONCEPTS_PATH", "data/clinical_concepts.yaml")
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Biomedical embedding ablation (PRD-110/ARCH-041)")
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    parser.add_argument("--concepts-path", type=Path, default=_DEFAULT_CONCEPTS_PATH)
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.model_ablation_backend == "stub":
        print(
            "[model-ablation] MODEL_ABLATION_BACKEND=stub — using deterministic fake "
            "embeddings, not real SapBERT/MedCPT. Set MODEL_ABLATION_BACKEND=local for "
            "a real run.",
            file=sys.stderr,
        )
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_guideline_collection,
    )

    with session_scope() as session:
        result = run_full_ablation(session, store, concepts_path=args.concepts_path)

    if not result.multi_stage_available:
        print(
            f"[model-ablation] panel B multi-stage skipped — {args.concepts_path} is not "
            "attested (see app.eval.orchestration_ablation.ablation.load_attested_vocabulary)",
            file=sys.stderr,
        )

    if result.n_questions == 0:
        print(
            "[model-ablation] no well_supported auto_generated questions with a "
            "gold_relevant_chunks set found — run the auto-seed pipeline first "
            "(app.eval.auto_seed).",
            file=sys.stderr,
        )
        return 1

    print(f"[model-ablation] ranked {result.n_questions} calibration question(s)...")
    if result.multi_stage_available:
        print(
            f"[model-ablation] multi-stage (vocabulary augmentation) fired on "
            f"{result.multi_stage_fired_rate:.1%} of questions"
        )
    paths = generate_reports(result, args.out_dir)
    for path in paths:
        print(f"[model-ablation] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
