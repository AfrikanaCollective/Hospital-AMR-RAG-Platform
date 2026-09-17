"""CLI: python -m scripts.run_model_ablation [--out-dir DIR]
(PRD-110 / ARCH-041; Makefile `make model-ablation-report`).

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
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.eval.model_ablation.ablation import run_full_ablation
from app.eval.model_ablation.report import generate_reports
from app.retrieval.vectorstore import QdrantVectorStore

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "app/eval/model_ablation/reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Biomedical embedding ablation (PRD-110/ARCH-041)")
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
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
        result = run_full_ablation(session, store)

    if result.n_questions == 0:
        print(
            "[model-ablation] no well_supported auto_generated questions with a "
            "gold_relevant_chunks set found — run the auto-seed pipeline first "
            "(app.eval.auto_seed).",
            file=sys.stderr,
        )
        return 1

    print(f"[model-ablation] ranked {result.n_questions} calibration question(s)...")
    paths = generate_reports(result, args.out_dir)
    for path in paths:
        print(f"[model-ablation] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
