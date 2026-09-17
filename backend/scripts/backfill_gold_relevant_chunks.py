"""One-off backfill: `EvalQuestion.gold_relevant_chunks` for auto-seeded
rows created before DEVIATIONS.md #122's fix (PRD-109/ARCH-040, Phase 6).

`app.eval.auto_seed._generate_one_scenario` now writes this field itself at
creation time (from that same scenario's own `Result.citations`) — this
script only backfills rows written *before* that fix. Idempotent and
additive: only touches a row where `gold_relevant_chunks IS NULL` and its
linked `Result` has at least one citation; never overwrites an
already-populated value. Safe to re-run (a no-op once every eligible row is
filled).

Usage: python -m scripts.backfill_gold_relevant_chunks [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.models.eval import EvalQuestion, Result
from app.db.session import session_scope


def backfill(dry_run: bool = False) -> int:
    with session_scope() as session:
        stmt = (
            select(EvalQuestion, Result)
            .join(Result, Result.eval_question_id == EvalQuestion.id)
            .where(EvalQuestion.gold_relevant_chunks.is_(None))
        )
        rows = session.execute(stmt).all()
        updated = 0
        for question, result in rows:
            if not result.citations:
                continue
            gold = sorted({c["chunk_id"] for c in result.citations})
            print(f"[backfill] {question.id}: gold_relevant_chunks <- {gold}")
            if not dry_run:
                question.gold_relevant_chunks = gold
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

    updated = backfill(dry_run=args.dry_run)
    print(f"[backfill] {'would update' if args.dry_run else 'updated'} {updated} question(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
