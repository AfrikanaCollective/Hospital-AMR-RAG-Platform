"""CLI: python -m scripts.run_orchestration_ablation [--out-dir DIR]
[--concepts-path PATH] (PRD-111; PHASE7-PROPOSAL.md; Makefile
`make orchestration-ablation-report`).

Runs the single-stage / criteria-reuse / operator-vocabulary ablation
against the real Qdrant guideline collection and the real
`eval.eval_question` table, then writes the PHASE7-PROPOSAL.md report PNG.

Needs a real Postgres + Qdrant with an already-ingested guideline corpus and
an already-seeded auto-generated question set — not runnable against
`:memory:`/stub backends, which is what `tests/test_orchestration_ablation.py`
covers instead (CLAUDE.md §5). Requires the `retrieval-tuning` optional
extra (seaborn/pandas/matplotlib).

**Arm C (operator-vocabulary) requires `data/clinical_concepts.yaml` to be
attested** (every `TODO_CONFIRM` replaced by the operator, PHASE7-PROPOSAL.md
§4). If it isn't, this script still produces a report for Arms A/B and prints
why Arm C was skipped — it never runs Arm C against a placeholder.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.eval.orchestration_ablation.ablation import run_full_ablation
from app.eval.orchestration_ablation.report import generate_report
from app.retrieval.vectorstore import QdrantVectorStore

# CWD-relative, not `__file__`-relative (DEVIATIONS.md #150): the real
# invocation environment is `docker compose exec api ...` with
# WORKDIR=/app, where `data/` is a direct child (bind-mounted) and this
# script lives at `/app/scripts/...` -- not the host's `backend/scripts/`
# layout, where `data/` is a sibling of `backend/`. `__file__`-relative
# `.parent` math computed a path correct for one layout and wrong for the
# other; a plain relative default resolves correctly against either cwd
# (`/app` in the container; `backend/` on the host, overridden via env/flag
# there) -- same pattern as `scripts/prepare_sample_guidelines.py`'s
# `SAMPLE_GUIDELINES_DIR`.
_DEFAULT_OUT_DIR = Path(
    os.environ.get("ORCHESTRATION_ABLATION_OUT_DIR", "app/eval/orchestration_ablation/reports")
)
_DEFAULT_CONCEPTS_PATH = Path(
    os.environ.get("CLINICAL_CONCEPTS_PATH", "data/clinical_concepts.yaml")
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Single-stage vs. multi-step orchestration ablation (PRD-111)"
    )
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    parser.add_argument("--concepts-path", type=Path, default=_DEFAULT_CONCEPTS_PATH)
    args = parser.parse_args(argv)

    settings = get_settings()
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_guideline_collection,
    )

    with session_scope() as session:
        result = run_full_ablation(session, store, concepts_path=args.concepts_path)

    if not result.vocabulary_attested:
        print(
            f"[orchestration-ablation] Arm C (operator-vocabulary) skipped — "
            f"{args.concepts_path} is not attested: {result.vocabulary_error}",
            file=sys.stderr,
        )

    if result.well_supported.n_questions == 0:
        print(
            "[orchestration-ablation] no well_supported auto_generated questions with a "
            "gold_relevant_chunks set found — run the auto-seed pipeline first "
            "(app.eval.auto_seed).",
            file=sys.stderr,
        )
        return 1

    print(
        f"[orchestration-ablation] well_supported: {result.well_supported.n_questions} "
        f"question(s); missing_info_expected: {result.missing_info.n_questions} question(s)"
    )
    path = generate_report(result.well_supported, result.missing_info, args.out_dir)
    print(f"[orchestration-ablation] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
