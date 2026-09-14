"""Document parsing — .md (fixtures) and .pdf (hand-built minimal PDFs) (ARCH §5.1)."""

from __future__ import annotations

from pathlib import Path

from app.ingestion.pdf_parse import parse_document, parse_markdown, parse_pdf
from tests.pdf_helpers import make_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "guidelines"


def test_parse_markdown_fixture_detects_headings_and_is_fully_extractable() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-002_hospital_acquired_infection.md"))
    assert doc.parse_quality == 1.0
    headings = {s["heading"] for s in doc.sections}
    assert "Investigations" in headings
    assert "Antimicrobial choice" in headings
    assert "Required information" in headings
    investigations = next(s for s in doc.sections if s["heading"] == "Investigations")
    assert investigations["number"] == "2"


def test_parse_document_dispatches_on_suffix() -> None:
    doc = parse_document(str(FIXTURES / "SYNTH-GL-001_acute_breathlessness.md"))
    assert doc.page_count >= 1


def test_parse_pdf_extracts_text_and_detects_whole_line_heading(tmp_path: Path) -> None:
    pdf_path = make_pdf(
        [
            "1 Introduction",
            "This guideline recommends recording vital signs on arrival.",
            "1.1 Immediate observations",
            "Record respiratory rate and oxygen saturation.",
        ],
        tmp_path / "sample.pdf",
    )
    doc = parse_pdf(str(pdf_path))
    assert doc.page_count == 1
    assert "recording vital signs" in doc.normalized_text
    numbers = {s["number"] for s in doc.sections}
    assert "1" in numbers
    assert "1.1" in numbers
    assert 0.0 <= doc.parse_quality <= 1.0
    assert doc.source_path == str(pdf_path)


def test_parse_pdf_low_quality_when_mostly_empty(tmp_path: Path) -> None:
    pdf_path = make_pdf([], tmp_path / "empty.pdf")
    doc = parse_pdf(str(pdf_path))
    assert doc.parse_quality < 0.5


def test_page_for_offset_maps_correctly() -> None:
    doc = parse_markdown(str(FIXTURES / "SYNTH-GL-003_narrow_topic_electrolytes.md"))
    assert doc.page_for_offset(0) == 1
    assert doc.page_for_offset(len(doc.normalized_text) - 1) >= 1
