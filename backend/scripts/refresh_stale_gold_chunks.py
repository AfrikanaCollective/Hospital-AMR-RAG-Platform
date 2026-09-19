"""One-off maintenance: re-derive `EvalQuestion.gold_relevant_chunks` for rows
whose recorded chunk ids no longer resolve against the live `corpus.chunk`
table (PRD-109/ARCH-040, DEVIATIONS.md #164).

Distinct from `backfill_gold_relevant_chunks.py`, which only fills rows where
the field is `NULL`. This script targets a different failure mode found via
the Phase 6 retrieval-tuning report: a row can have a non-empty
`gold_relevant_chunks` that was valid when captured, but no longer resolves
to any real chunk — e.g. found live on 2026-09-19 for 21 of 73 calibration
questions, all created 2026-09-15/16, referencing chunk ids absent from both
the Postgres `chunk` table and the Qdrant collection (confirmed not a
`vector_id`/`id` mixup either — see DEVIATIONS.md #164 for what was ruled
out). Such a question can never score a recall/MRR hit under any retrieval
method, dragging down every aggregate metric regardless of retrieval quality.

Re-derives via the same mechanism `app.eval.tasks._capture_gold_relevant_chunks`
already uses at question-creation time: invoke the real pipeline with the
question's own (already-generated) text and take its fresh, grounding-verified
citations as the new gold set. Idempotent: a row where every existing gold
chunk id still resolves is left untouched; safe to re-run.

Usage: python -m scripts.refresh_stale_gold_chunks [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.models.corpus import Chunk
from app.db.models.eval import EvalQuestion
from app.db.session import session_scope
from app.eval.tasks import _capture_gold_relevant_chunks


def refresh(dry_run: bool = False) -> int:
    with session_scope() as session:
        valid_chunk_ids = {str(cid) for (cid,) in session.execute(select(Chunk.id)).all()}

        stmt = select(EvalQuestion).where(EvalQuestion.gold_relevant_chunks.isnot(None))
        rows = session.execute(stmt).scalars().all()

        updated = 0
        for row in rows:
            existing = set(row.gold_relevant_chunks or [])
            if not existing or existing <= valid_chunk_ids:
                continue  # empty or every id still resolves -- nothing stale here

            fresh = _capture_gold_relevant_chunks(row.text)
            print(f"[refresh] {row.id}: stale gold_relevant_chunks={sorted(existing)} -> {fresh}")
            if not dry_run:
                row.gold_relevant_chunks = fresh
            updated += 1

        if dry_run:
            session.rollback()
        return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change, commit nothing"
    )
    args = parser.parse_args(argv)

    updated = refresh(dry_run=args.dry_run)
    print(f"[refresh] {'would update' if args.dry_run else 'updated'} {updated} question(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
