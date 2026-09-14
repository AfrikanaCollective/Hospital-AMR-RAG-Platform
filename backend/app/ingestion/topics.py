"""Lightweight topic tagging for coverage tracking (ARCH §5.1 step 5; used by §15).

"a lightweight taxonomy (section headings + keyword map)" — rather than
inventing a new keyword vocabulary (a real risk of getting clinical
categorisation subtly wrong), this reuses the operator-curated `topic_tags`
list already declared per document in the ingest manifest (ARCH-038) as the
map: each of *that document's own* topic phrases is checked against a
chunk's heading + text, so tagging never invents a category the operator
didn't already assert applies to this document (DEVIATIONS.md #58).
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"and", "of", "the", "a", "an", "in", "for", "with", "or", "to", "on"}
_MIN_MATCH_FRACTION = 0.5  # at least half the tag phrase's significant words must appear
_MIN_WORD_LENGTH = 3


def _significant_words(phrase: str) -> set[str]:
    tokens = _WORD_RE.findall(phrase.lower())
    return {w for w in tokens if w not in _STOPWORDS and len(w) >= _MIN_WORD_LENGTH}


def _tag_matches(tag: str, haystack_words: set[str]) -> bool:
    words = _significant_words(tag)
    if not words:
        return False
    overlap = words & haystack_words
    return len(overlap) >= max(1, round(len(words) * _MIN_MATCH_FRACTION))


def assign_topic_tags(
    chunk_text: str, heading: str | None, document_topic_tags: list[str]
) -> list[str]:
    """The subset of `document_topic_tags` whose significant words appear in
    this chunk's heading + text."""
    if not document_topic_tags:
        return []
    haystack = f"{heading or ''} {chunk_text}".lower()
    haystack_words = set(_WORD_RE.findall(haystack))
    return [tag for tag in document_topic_tags if _tag_matches(tag, haystack_words)]
