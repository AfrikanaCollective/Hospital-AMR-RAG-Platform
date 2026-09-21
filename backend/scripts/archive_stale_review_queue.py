"""One-off maintenance: archive every currently-`open` `eval.Result` review-
queue item (DEVIATIONS.md #185).

**Root cause**: this session's guideline-corpus restructuring (DEVIATIONS.md
#170-#175 — documents retired, renamed, split into `source_pages` excerpts)
happened entirely independently of the review queue. Every open queue item
was created 2026-09-15/17 by `app.eval.auto_seed`, before any of that work —
their `Result.citations` are a point-in-time snapshot (`app.schemas.citation.
Citation.document_title`/`chunk_id`, captured at generation time, never
live-joined), so all 71 open results that carry citations now reference a
`chunk_id` that no longer exists in `corpus.chunk`, under 3 document titles
that don't match any of the current 5-document corpus at all. The remaining
29 (`no_guideline_expected`/`missing_info_expected`, no citations by design)
were also generated against that same superseded corpus, so their outcome
isn't trustworthy either — operator decision (2026-09-21): archive all 100,
not just the 71 with a dangling citation.

**Why `queue_state = "archived"`, not a new state**: `Result.queue_state`'s
vocabulary is exactly `not_queued | open | archived`
(`app/db/models/eval.py`), and no 4th "stale/retired" value exists in the
schema — adding one is a real, separate migration this maintenance action
doesn't need. `archived` is the closest existing meaning ("no longer in the
active queue") and is a plain mutable column, not an append-only-audit table
(CLAUDE.md §3.6 only binds `audit.audit_event`).

**Real gap flagged, not fixed**: normal archival
(`app.rubric.workflow.compute_result_irr_and_archive`) also writes an
`eval.ResultArchive` row (rating history + IRR snapshot) and is what
`app.rubric.tasks._fetch_archived_results_for_slice` expects when computing
slice-level IRR. This script does NOT write a `ResultArchive` row for these
100 rows — they were never rated, so there is no rating history or IRR to
snapshot; writing an empty/fake one would misrepresent a real review cycle
that didn't happen. Contribution to a slice-level IRR computation is
harmless (an unrated result has no `rating_round` rows, so it contributes
zero data points to `per_domain_irr`), but a naive `count(*) where
queue_state='archived'` used as a proxy for "reviews completed" would be
inflated by these 100 rows going forward. Not fixed here — out of scope for
a maintenance script, and this class of query does not exist yet anywhere in
this codebase to fix.

**Leaves the underlying de-identified source records/`EvalQuestion` rows
alone** — only `Result.queue_state` changes. Refilling the queue with fresh,
accurate results (re-running `app.eval.auto_seed` against the current
corpus) is a separate, explicitly-deferred decision (real LLM-gateway calls,
real minutes) — not done by this script.

Usage: python -m scripts.archive_stale_review_queue [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.corpus import Chunk
from app.db.models.eval import Result
from app.db.session import session_scope


def _citations_reference_a_dangling_chunk(session: Session, result: Result) -> bool:
    chunk_ids = {c["chunk_id"] for c in result.citations if c.get("chunk_id")}
    if not chunk_ids:
        return False
    existing = session.execute(select(Chunk.id).where(Chunk.id.in_(chunk_ids))).scalars().all()
    return len(existing) < len(chunk_ids)


def archive_open_queue(*, dry_run: bool = False) -> int:
    with session_scope() as session:
        open_results = (
            session.execute(select(Result).where(Result.queue_state == "open")).scalars().all()
        )
        if not open_results:
            print("[archive-stale-review-queue] no open results found -- nothing to do")
            return 0

        stale = sum(1 for r in open_results if _citations_reference_a_dangling_chunk(session, r))
        print(
            f"[archive-stale-review-queue] {len(open_results)} open result(s), "
            f"{stale} with a citation to a chunk no longer in the current corpus"
        )

        if dry_run:
            print("[archive-stale-review-queue] --dry-run: no changes made")
            return 0

        for r in open_results:
            r.queue_state = "archived"

    print(f"[archive-stale-review-queue] archived {len(open_results)} result(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would be archived, commit nothing"
    )
    args = parser.parse_args(argv)
    return archive_open_queue(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
