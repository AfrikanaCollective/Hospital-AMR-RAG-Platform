"""Page-provenance remapping for partial-page-extract guideline ingestion
(ARCH-038 extension, DEVIATIONS.md #166)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.page_provenance import (
    PageProvenanceError,
    apply_source_pages,
    load_source_pages,
)
from app.ingestion.pdf_parse import ParsedDocument


def _doc(page_starts: list[tuple[int, int]], sections: list[dict] | None = None) -> ParsedDocument:
    return ParsedDocument(
        normalized_text="x" * 100,
        sections=sections or [],
        page_count=len(page_starts),
        parse_quality=1.0,
        page_starts=page_starts,
    )


def _write_manifest(dir_: Path, files: dict) -> None:
    (dir_ / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")


class TestLoadSourcePages:
    def test_no_manifest_file_returns_none(self, tmp_path: Path) -> None:
        assert load_source_pages(tmp_path, "doc.pdf") is None

    def test_no_entry_for_file_returns_none(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, {"other.pdf": {"source_pages": [1, 2]}})
        assert load_source_pages(tmp_path, "doc.pdf") is None

    def test_entry_without_source_pages_returns_none(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, {"doc.pdf": {"title": "Doc"}})
        assert load_source_pages(tmp_path, "doc.pdf") is None

    def test_entry_with_source_pages_returns_list(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, {"doc.pdf": {"source_pages": [42, 43, 44, 45]}})
        assert load_source_pages(tmp_path, "doc.pdf") == [42, 43, 44, 45]

    def test_empty_source_pages_list_returns_none(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, {"doc.pdf": {"source_pages": []}})
        assert load_source_pages(tmp_path, "doc.pdf") is None


class TestApplySourcePages:
    def test_remaps_page_starts(self) -> None:
        doc = _doc([(1, 0), (2, 25), (3, 50), (4, 75)])
        apply_source_pages(doc, [42, 43, 44, 45])
        assert doc.page_starts == [(42, 0), (43, 25), (44, 50), (45, 75)]

    def test_page_for_offset_reflects_remap(self) -> None:
        doc = _doc([(1, 0), (2, 25), (3, 50), (4, 75)])
        apply_source_pages(doc, [42, 43, 44, 45])
        assert doc.page_for_offset(0) == 42
        assert doc.page_for_offset(30) == 43
        assert doc.page_for_offset(99) == 45

    def test_recomputes_section_page_numbers(self) -> None:
        sections = [{"heading": "Diagnosis", "char_start": 30, "char_end": 60}]
        doc = _doc([(1, 0), (2, 25), (3, 50), (4, 75)], sections=sections)
        apply_source_pages(doc, [42, 43, 44, 45])
        assert doc.sections[0]["page_start"] == 43
        assert doc.sections[0]["page_end"] == 44

    def test_page_count_mismatch_raises(self) -> None:
        doc = _doc([(1, 0), (2, 25), (3, 50), (4, 75)])
        with pytest.raises(PageProvenanceError, match="4 page"):
            apply_source_pages(doc, [42, 43, 44])

    def test_non_positive_int_raises(self) -> None:
        doc = _doc([(1, 0), (2, 25)])
        with pytest.raises(PageProvenanceError, match="positive integers"):
            apply_source_pages(doc, [42, -1])

    def test_non_ascending_order_raises(self) -> None:
        doc = _doc([(1, 0), (2, 25), (3, 50)])
        with pytest.raises(PageProvenanceError, match="ascending"):
            apply_source_pages(doc, [44, 42, 43])

    def test_equal_run_is_allowed(self) -> None:
        """A duplicated physical page (e.g. a reprinted page) is a legitimate,
        if rare, extraction — non-decreasing is the real constraint, not
        strictly increasing."""
        doc = _doc([(1, 0), (2, 25), (3, 50)])
        apply_source_pages(doc, [42, 42, 43])
        assert doc.page_starts == [(42, 0), (42, 25), (43, 50)]

    def test_single_page_document(self) -> None:
        doc = _doc([(1, 0)])
        apply_source_pages(doc, [47])
        assert doc.page_starts == [(47, 0)]
