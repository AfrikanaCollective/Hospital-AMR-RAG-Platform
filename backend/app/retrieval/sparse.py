"""BM25-style sparse vectors over a clinical-aware analyzer (ARCH §6 "Sparse / BM25").

Term -> index uses a **stable hash**, not a fitted, corpus-local vocabulary
(DEVIATIONS.md #48 — supersedes an earlier per-batch-fit design that had a
real correctness bug: a Qdrant collection is shared across every ingested
`document_version`, and two independently-fitted local vocabularies — e.g. one
per ingestion batch — silently assign the SAME term DIFFERENT indices in
different chunks, corrupting sparse dot-product scores across documents once
they share a collection. A stable hash guarantees the same term always maps to
the same index everywhere, with no vocabulary to persist or keep in sync
between ingest and query time.

Each chunk's sparse vector stores raw term frequency; Qdrant's server-side
`Modifier.IDF` (set on the collection's `sparse` vector field —
`app.retrieval.vectorstore.QdrantVectorStore.ensure_collection`) multiplies by
the corpus's own IDF at query time, computed from what is actually indexed —
Qdrant's documented pattern for BM25-like sparse search. This is TF x
server-computed-IDF, not the full saturating BM25 formula (no per-document
length normalisation / k1 term) — "BM25-style", not an exact match to the
textbook formula; simpler and more correct-by-construction than fitting and
persisting our own BM25 statistics across ingestion batches.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

# Light stopwording only — clinical terms, drug names, numbers/units, and
# hyphenated compounds must survive (ARCH §6).
_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "with",
    "for",
    "on",
    "at",
    "by",
    "from",
    "as",
    "it",
    "its",
    "which",
    "if",
    "not",
    "can",
    "may",
    "also",
    "will",
    "should",
}
# Keeps hyphenated/slash-joined tokens intact (drug names, mg/kg-style dosage
# units) and numbers, per ARCH §6's analyzer spec.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")

SPARSE_DIM = 2**24  # hash space; collisions astronomically unlikely for a guideline vocabulary


def analyze(text: str) -> list[str]:
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if t not in _STOPWORDS and (len(t) > 1 or t.isdigit())
    ]


def _term_index(term: str) -> int:
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % SPARSE_DIM


def doc_sparse_vector(text: str) -> dict:
    """Raw term-frequency sparse vector for one chunk's text."""
    counts = Counter(analyze(text))
    indices = [_term_index(t) for t in counts]
    values = [float(c) for c in counts.values()]
    return {"indices": indices, "values": values}


def query_sparse_vector(query: str) -> dict:
    """Term-presence sparse vector for a query (each distinct term weight 1.0)."""
    terms = sorted(set(analyze(query)))
    indices = [_term_index(t) for t in terms]
    values = [1.0] * len(indices)
    return {"indices": indices, "values": values}
