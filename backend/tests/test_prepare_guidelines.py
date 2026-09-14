"""prepare_sample_guidelines behaviour (DEVIATIONS #26; ARCH-038)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.prepare_sample_guidelines import (
    REQUIRED_MANIFEST_FIELDS,
    _entry_incomplete,
    _is_guideline_file,
    main,
)

REPO = Path(__file__).resolve().parents[2]


def test_manifest_example_is_valid_and_covers_required_fields() -> None:
    data = json.loads((REPO / "data/sample_guidelines/manifest.example.json").read_text())
    assert "files" in data and data["files"]
    for name, entry in data["files"].items():
        assert name.lower().endswith((".pdf", ".md"))
        for f in REQUIRED_MANIFEST_FIELDS:
            assert f in entry, f"{name} missing manifest field {f}"


def test_entry_incomplete_flags_placeholders_and_missing() -> None:
    assert set(_entry_incomplete(None)) == set(REQUIRED_MANIFEST_FIELDS)
    assert "licence" in _entry_incomplete(
        {
            "title": "t",
            "publisher": "p",
            "version_label": "v",
            "effective_date": "2024-01-01",
            "licence": "TODO_CONFIRM (WHO)",
        }
    )
    assert (
        _entry_incomplete(
            {
                "title": "t",
                "publisher": "p",
                "version_label": "v",
                "effective_date": "2024-01-01",
                "licence": "CC BY-NC-SA 3.0 IGO",
            }
        )
        == []
    )


def test_synth_fixtures_are_not_treated_as_corpus_docs() -> None:
    assert not _is_guideline_file(Path("SYNTH-GL-001_x.md"))
    assert not _is_guideline_file(Path("SOURCES.md"))
    assert _is_guideline_file(Path("Some Real Guideline (2024).pdf"))


def test_no_docs_no_flag_exits_nonzero(tmp_path: Path) -> None:
    empty = tmp_path / "gl"
    rc = main(["--dir", str(empty)])
    assert rc == 2


def test_allow_synthetic_writes_ci_fixtures_not_into_corpus(tmp_path: Path) -> None:
    empty = tmp_path / "gl"
    rc = main(["--dir", str(empty), "--allow-synthetic"])
    assert rc == 0
    # fixtures land under backend/tests/fixtures/guidelines/, never in --dir
    assert not any(empty.glob("SYNTH-GL-*.md"))
    fixtures = REPO / "backend/tests/fixtures/guidelines"
    assert (fixtures / "SYNTH-GL-001_acute_breathlessness.md").exists()
