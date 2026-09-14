"""Chunk-level topic tagging from the document's own manifest topic_tags
(ARCH §5.1 step 5; DEVIATIONS.md #58)."""

from __future__ import annotations

from app.ingestion.topics import assign_topic_tags

DOC_TAGS = [
    "neonatal jaundice",
    "vitamin K prophylaxis",
    "newborn resuscitation",
    "suspected neonatal sepsis",
]


def test_chunk_matching_a_tags_significant_words_is_tagged() -> None:
    tags = assign_topic_tags(
        "Phototherapy is recommended for infants with significant jaundice.",
        "Management of neonatal jaundice",
        DOC_TAGS,
    )
    assert "neonatal jaundice" in tags


def test_chunk_matching_no_tags_gets_no_tags() -> None:
    tags = assign_topic_tags("This section discusses breastfeeding positioning.", None, DOC_TAGS)
    assert tags == []


def test_multi_word_tag_requires_partial_word_overlap_not_full_phrase() -> None:
    tags = assign_topic_tags(
        "Give vitamin K to all newborns shortly after birth to prevent bleeding.",
        None,
        DOC_TAGS,
    )
    assert "vitamin K prophylaxis" in tags


def test_no_document_tags_returns_empty_list() -> None:
    assert assign_topic_tags("Any content at all here.", "Any heading", []) == []


def test_multiple_tags_can_match_the_same_chunk() -> None:
    tags = assign_topic_tags(
        "Suspected neonatal sepsis requiring resuscitation and neonatal jaundice monitoring.",
        None,
        DOC_TAGS,
    )
    assert "suspected neonatal sepsis" in tags
    assert "neonatal jaundice" in tags
    # "newborn resuscitation": only "resuscitation" overlaps ("newborn" != "neonatal"),
    # but 1 of 2 significant words still clears the 50% threshold -> also tagged.
    assert "newborn resuscitation" in tags
