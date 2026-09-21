"""One-off maintenance: hard-remove a guideline document and all its chunks
from both Postgres and Qdrant (DEVIATIONS.md #170).

No code path in this codebase has ever needed to delete ingested content
before now — `app.ingestion.documents.create_or_supersede_document_version`'s
own supersession model deliberately keeps a superseded version's chunks and
vectors retrievable "so existing citations still resolve" (ARCH §5.1 step 6).
This script exists for the genuinely different case this supersession model
doesn't cover: the *source file itself* was deleted (not replaced by a newer
version) and the operator wants the document gone from the corpus entirely,
not superseded.

**Real gap this incidentally surfaced**: `app.ingestion.chunk_persistence`
writes each chunk's Qdrant payload `status: "active"` once, at ingest time,
and nothing ever updates it afterward -- not even on legitimate supersession.
Since `app.retrieval.hybrid.retrieve()` filters on `status=active`
(`flt.setdefault("status", "active")`), this means a *superseded* document's
old chunks are likely still being served by retrieval today, unfiltered by
Qdrant, because their payload was never told the Postgres row's status
changed. This script does not fix that (a real, separate, retrieval-path
change with its own testing needs) -- it hard-deletes rather than relying on
a status flag, which sidesteps the gap for this one document without fixing
it generally. Flagged, not fixed, in DEVIATIONS.md #170.

**Leaves `EvalQuestion.gold_relevant_chunks` alone.** Any eval question whose
gold chunks point at this document goes stale by removing it -- exactly the
DEVIATIONS.md #164 class of problem. Run `python -m
scripts.refresh_stale_gold_chunks` immediately after this script to re-derive
those questions' gold chunks against the now-current corpus.

Usage: python -m scripts.remove_document --title "<exact Document.title>" [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from qdrant_client.http import models as qm
from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models.corpus import Chunk, Document, DocumentVersion
from app.db.session import session_scope
from app.retrieval.vectorstore import QdrantVectorStore


def remove_document(title: str, *, dry_run: bool = False) -> int:
    settings = get_settings()
    store = QdrantVectorStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection=settings.qdrant_guideline_collection,
    )

    with session_scope() as session:
        document = session.execute(
            select(Document).where(Document.title == title)
        ).scalar_one_or_none()
        if document is None:
            print(f"[remove-document] no document with title={title!r} found", file=sys.stderr)
            return 1

        versions = (
            session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            )
            .scalars()
            .all()
        )

        chunk_ids: list[str] = []
        for version in versions:
            chunks = (
                session.execute(select(Chunk).where(Chunk.document_version_id == version.id))
                .scalars()
                .all()
            )
            chunk_ids.extend(str(c.id) for c in chunks)

        print(
            f"[remove-document] document={document.id} title={document.title!r} "
            f"source_uri={document.source_uri!r}"
        )
        print(f"[remove-document] {len(versions)} version(s), {len(chunk_ids)} chunk(s)")

        if dry_run:
            print("[remove-document] --dry-run: no changes made")
            return 0

        if chunk_ids:
            store._client.delete(  # noqa: SLF001 - no delete method on the VectorStore Protocol yet
                collection_name=settings.qdrant_guideline_collection,
                points_selector=qm.PointIdsList(points=chunk_ids),
            )
        # Explicit Core-style deletes, in FK dependency order (chunk -> document_version ->
        # document), executed immediately rather than via session.delete() -- the ORM unit of
        # work does not reliably infer this ordering from a plain FK column with no declared
        # relationship(), which previously caused a commit-time ForeignKeyViolation after the
        # Qdrant delete above had already gone through (non-transactional, unrecoverable) --
        # see DEVIATIONS.md #170.
        version_ids = [v.id for v in versions]
        if version_ids:
            session.execute(delete(Chunk).where(Chunk.document_version_id.in_(version_ids)))
            session.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
        session.execute(delete(Document).where(Document.id == document.id))

    print(
        f"[remove-document] removed {len(chunk_ids)} chunk(s), {len(versions)} version(s), "
        "1 document. Run `python -m scripts.refresh_stale_gold_chunks` next -- any eval "
        "question that referenced this document's chunks is now stale."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="exact Document.title to remove")
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would be removed, commit nothing"
    )
    args = parser.parse_args(argv)
    return remove_document(args.title, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
