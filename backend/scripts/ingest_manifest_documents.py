"""Ingest every complete manifest entry in SAMPLE_GUIDELINES_DIR that isn't
already in the corpus (DEVIATIONS.md #174, ARCH-038).

No prior code path drives ingestion straight from `manifest.json` -- the only
existing ingestion path is `POST /ingest/documents`, one file at a time, with
metadata supplied as HTTP form fields (an admin fills them in by hand, using
the manifest only as their own reference); `scripts/prepare_sample_guidelines.py`
reads the manifest only to validate it, never to ingest anything. This script
reuses the manifest's own metadata directly, so a manifest entry that
`prepare_sample_guidelines --strict` already accepts as complete does not
need to be re-typed into a form.

Reuses `app.ingestion.documents.create_or_supersede_document_version` +
`app.ingestion.tasks._run_process_document` unchanged -- the exact same
parse -> chunk -> embed -> persist -> upsert pipeline the HTTP route
triggers, just invoked synchronously and driven by the manifest instead of
by an admin's form submission. `create_or_supersede_document_version`'s own
idempotency (a no-op when `content_sha256` already matches an ingested
version) is what makes this safe to re-run over the whole manifest, not a
separate check this script implements -- an already-ingested file is
skipped naturally, not specially.

An incomplete manifest entry (any `TODO_CONFIRM`/missing required field) is
skipped with a warning, never ingested with invented metadata (ARCH-038) --
the same `_entry_incomplete` check `prepare_sample_guidelines.py` uses.

Each document is processed in its own `session_scope()` -- Qdrant's upsert is
not transactional with the Postgres commit (the same reason `remove_document.py`
processes one document_version at a time), so one document's failure must not
roll back another document already successfully ingested in the same run.

Usage: python -m scripts.ingest_manifest_documents [--dir DIR] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.db.session import session_scope
from app.ingestion.documents import DocumentMetadata, create_or_supersede_document_version
from app.ingestion.tasks import _run_process_document
from scripts.prepare_sample_guidelines import _entry_incomplete


def _load_manifest(dir_: Path) -> dict:
    mf = dir_ / "manifest.json"
    if not mf.exists():
        return {}
    return json.loads(mf.read_text(encoding="utf-8")).get("files", {})


def _build_metadata(path: Path, entry: dict) -> DocumentMetadata:
    raw_date = entry.get("effective_date")
    effective_date = date.fromisoformat(raw_date) if raw_date else None
    return DocumentMetadata(
        title=entry["title"],
        publisher=entry.get("publisher"),
        external_ref=entry.get("external_ref"),
        source_uri=str(path),
        licence=entry.get("licence"),
        version_label=entry["version_label"],
        effective_date=effective_date,
        topic_tags=entry.get("topic_tags", []),
        format_profile=entry.get("format_profile"),
    )


def ingest_all(dir_: Path, *, dry_run: bool = False) -> int:
    manifest = _load_manifest(dir_)
    if not manifest:
        print(f"[ingest] no manifest.json (or no files) in {dir_}", file=sys.stderr)
        return 1

    ingested = 0
    for filename, entry in manifest.items():
        path = dir_ / filename
        if not path.exists():
            print(f"[ingest] SKIP {filename!r}: not found on disk", file=sys.stderr)
            continue
        missing = _entry_incomplete(entry)
        if missing:
            print(f"[ingest] SKIP {filename!r}: incomplete manifest ({', '.join(missing)})")
            continue

        content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        meta = _build_metadata(path, entry)

        if dry_run:
            print(f"[ingest] would process {filename!r} (sha256={content_sha256[:12]}...)")
            continue

        with session_scope() as session:
            version, created = create_or_supersede_document_version(
                session, meta, content_sha256=content_sha256
            )
            if not created:
                print(f"[ingest] SKIP {filename!r}: already ingested (content_sha256 matches)")
                continue
            rows = _run_process_document(session, str(version.id), topic_tags=meta.topic_tags)
            print(
                f"[ingest] {filename!r}: {len(rows)} chunk(s) persisted "
                f"(document_version={version.id})"
            )
            ingested += 1

    print(f"[ingest] {'would ingest' if dry_run else 'ingested'} {ingested} new document(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path(get_settings().sample_guidelines_dir))
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would be ingested, commit nothing"
    )
    args = parser.parse_args(argv)
    return ingest_all(args.dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
