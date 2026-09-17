"""CLI: python -m scripts.run_retrieval_weight_sweep [--out-dir DIR]
(Phase 6, PRD-109 / ARCH-040; Makefile `make retrieval-tuning-report`).

Runs the offline BM25/vector weight sweep against the real Qdrant guideline
collection and the real `eval.eval_question` table (well_supported,
auto_generated, non-empty gold_relevant_chunks — see
`app.eval.retrieval_tuning.sweep.fetch_calibration_questions`), then writes
the three PHASE6-PROPOSAL.md report PNGs.

Needs a real Postgres + Qdrant with an already-ingested guideline corpus and
an already-seeded auto-generated question set (`make eval` / the auto-seed
task) — not runnable against `:memory:`/stub backends, which is what
`tests/test_retrieval_tuning.py` covers instead (CLAUDE.md §5). Requires the
`retrieval-tuning` optional extra (seaborn/pandas/matplotlib).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.eval.retrieval_tuning.report import generate_reports
from app.eval.retrieval_tuning.sweep import fetch_calibration_questions, rank_question, run_sweep
from app.retrieval.vectorstore import QdrantVectorStore

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "app/eval/retrieval_tuning/reports"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 6 retrieval weight/depth sweep.")
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    settings = get_settings()
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_guideline_collection,
    )

    with session_scope() as session:
        questions = fetch_calibration_questions(session)
    if not questions:
        print(
            "[retrieval-tuning] no well_supported auto_generated questions with a "
            "gold_relevant_chunks set found — run the auto-seed pipeline first "
            "(app.eval.auto_seed).",
            file=sys.stderr,
        )
        return 1

    print(f"[retrieval-tuning] sweeping {len(questions)} calibration question(s)...")
    rankings = [rank_question(store, q) for q in questions]
    result = run_sweep(rankings)

    paths = generate_reports(result, args.out_dir)
    for path in paths:
        print(f"[retrieval-tuning] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
