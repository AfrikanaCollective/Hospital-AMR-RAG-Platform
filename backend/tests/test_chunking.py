"""Format-profile-aware chunking (ARCH §6, ARCH-013; PRD-004)."""

from __future__ import annotations

from pathlib import Path

from app.ingestion.chunking import chunk_document
from app.ingestion.pdf_parse import parse_markdown

FIXTURES = Path(__file__).parent / "fixtures" / "guidelines"


def _by_type(chunks: list[dict], chunk_type: str) -> list[dict]:
    return [c for c in chunks if c["chunk_type"] == chunk_type]


def test_grade_marker_numbered_clause_becomes_recommendation_chunk() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-002_hospital_acquired_infection.md"))
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    recs = _by_type(chunks, "recommendation")
    assert len(recs) == 1
    assert recs[0]["text"].startswith("2.1.1")
    assert "Strong recommendation" in recs[0]["text"]
    assert recs[0]["section_number"] == "2"


def test_numbered_clause_without_grade_marker_stays_prose() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-002_hospital_acquired_infection.md"))
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    prose = _by_type(chunks, "prose")
    prose_texts = " ".join(c["text"] for c in prose)
    assert "3.1.1 Empirical antimicrobial choice" in prose_texts
    assert "4.1 Before a syndrome-specific" in prose_texts
    assert not any(c["chunk_type"] == "recommendation" for c in chunks if "3.1.1" in c["text"])


def test_table_under_criteria_heading_becomes_criteria_chunk() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-001_acute_breathlessness.md"))
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    criteria = _by_type(chunks, "criteria")
    assert len(criteria) == 1
    assert "Stage" in criteria[0]["text"]
    assert isinstance(criteria[0]["meta"]["criteria"], list)
    assert not _by_type(chunks, "table")  # reclassified, not double-counted


def test_embedding_text_prefixed_with_section_breadcrumb_but_text_stays_raw() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-003_narrow_topic_electrolytes.md"))
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    rec = _by_type(chunks, "recommendation")[0]
    assert rec["meta"]["embedding_text"].startswith(rec["section_path"])
    assert rec["meta"]["embedding_text"].endswith(rec["text"])
    assert not rec["text"].startswith(rec["section_path"])


def test_parent_linkage_within_a_section() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-002_hospital_acquired_infection.md"))
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    required_info_chunks = [c for c in chunks if c["heading"] == "Required information"]
    assert len(required_info_chunks) == 1  # single short paragraph -> single chunk
    assert required_info_chunks[0]["parent_ordinal"] is None  # first (only) chunk in its section


def test_protocol_step_profile_tags_numbered_clauses_without_grade_marker() -> None:
    text = (
        "## 1. Triage pathway\n\n"
        "1.1 Assess airway, breathing, circulation and record observations.\n\n"
        "1.2 If unstable, call for senior review immediately.\n"
    )
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
        path = f.name
    doc = parse_markdown(path)
    chunks = chunk_document(doc, format_profile="clinical_protocol")
    steps = _by_type(chunks, "protocol_step")
    assert len(steps) == 2
    assert steps[0]["text"].startswith("1.1")
    assert steps[1]["text"].startswith("1.2")
    assert steps[1]["parent_ordinal"] == steps[0]["ordinal"]


def test_oversized_recommendation_splits_and_tags_split_group_id() -> None:
    long_sentence = "This is a supporting clause about the recommendation context. "
    body = (
        "2.1.1 The guideline recommends the following approach. "
        + long_sentence * 200
        + "(Strong recommendation, low certainty)"
    )
    text = f"## 2. Long section\n\n{body}\n"
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
        path = f.name
    doc = parse_markdown(path)
    chunks = chunk_document(doc, format_profile="grade_recommendations")
    recs = _by_type(chunks, "recommendation")
    assert len(recs) > 1
    group_ids = {c["meta"]["split_group_id"] for c in recs}
    assert len(group_ids) == 1
    assert all(c["token_count"] <= 1024 for c in recs)


def test_prose_windowing_produces_multiple_overlapping_chunks() -> None:
    paragraphs = [
        f"Paragraph number {i} discusses a distinct clinical topic in some detail here."
        for i in range(90)
    ]
    text = "## 5. Narrative background\n\n" + "\n\n".join(paragraphs) + "\n"
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(text)
        path = f.name
    doc = parse_markdown(path)
    chunks = chunk_document(doc, format_profile="narrative")
    prose = _by_type(chunks, "prose")
    assert len(prose) > 1
    for c in prose:
        assert c["token_count"] <= 700  # target max 600 + overlap slack
    # adjacent windows share overlapping words (15% overlap, ARCH §6 rule 2)
    first_words = prose[0]["text"].split()
    second_words = prose[1]["text"].split()
    assert any(w in second_words[:30] for w in first_words[-15:])
