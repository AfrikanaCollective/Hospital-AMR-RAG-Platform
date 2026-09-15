"""Citation-verifier agent (ARCH §8.3, ARCH-015)."""

from __future__ import annotations

import app.agents.citation_verifier_agent as cva
from app.schemas.enums import EscalationTrigger

CHUNK = {
    "chunk_id": "ch1",
    "text": "Record respiratory rate at presentation for every neonate.",
    "document_id": "doc1",
    "document_title": "Newborn Care Guideline",
    "document_version_id": "v1",
    "version_label": "2021",
    "version_status": "active",
    "effective_date": None,
    "section_number": "3.2",
    "section_path": "Assessment > Vitals",
    "page_start": 5,
    "page_end": 5,
    "char_start": 100,
    "char_end": 200,
}

OTHER_CHUNK = {
    **CHUNK,
    "chunk_id": "ch2",
    "text": "Start empiric antibiotics within one hour of suspected sepsis.",
}


def test_all_supported_releases_and_builds_citations(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cva, "_ENTAILMENT_FN", lambda claim, quote: "yes")  # noqa: ARG005
    state = {
        "retrieval": [CHUNK],
        "candidate_segments": [
            {
                "type": "claim",
                "text": "record respiratory rate at presentation",
                "citation_ids": ["c1"],
                "quote": "Record respiratory rate at presentation",
            }
        ],
    }
    out = cva.run(state)  # type: ignore[arg-type]
    assert out["grounding_report"]["action"] == "release"
    assert "escalation" not in out
    assert len(out["candidate_citations"]) == 1
    assert out["candidate_citations"][0]["chunk_id"] == "ch1"


def test_over_cited_segment_drops_the_unverified_id(monkeypatch) -> None:  # noqa: ANN001
    """DEVIATIONS.md #107: a segment citing two ids where only one actually
    contains the quote is released (a segment is SUPPORTED if ANY cited id
    verifies) — but the unverified id must not survive into the returned
    segment, or the UI renders a footnote link with no citation behind it."""
    monkeypatch.setattr(cva, "_ENTAILMENT_FN", lambda claim, quote: "yes")  # noqa: ARG005
    state = {
        "retrieval": [CHUNK, OTHER_CHUNK],
        "candidate_segments": [
            {
                "type": "claim",
                "text": "record respiratory rate at presentation",
                "citation_ids": ["c1", "c2"],  # only c1's chunk has the quote
                "quote": "Record respiratory rate at presentation",
            }
        ],
    }
    out = cva.run(state)  # type: ignore[arg-type]
    assert out["grounding_report"]["action"] == "release"
    assert out["candidate_segments"][0]["citation_ids"] == ["c1"]
    assert [c["citation_id"] for c in out["candidate_citations"]] == ["c1"]


def test_scope_violation_escalates_with_safety_filter(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cva, "_ENTAILMENT_FN", lambda claim, quote: "yes")  # noqa: ARG005
    state = {
        "retrieval": [CHUNK],
        "candidate_segments": [
            {
                "type": "claim",
                "text": "You should start antibiotics now.",
                "citation_ids": ["c1"],
                "quote": "Record respiratory rate at presentation",
            }
        ],
    }
    out = cva.run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.SAFETY_FILTER


def test_unsupported_with_nothing_left_escalates_grounding_failure(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cva, "_ENTAILMENT_FN", lambda claim, quote: "yes")  # noqa: ARG005
    state = {
        "retrieval": [CHUNK],
        "candidate_segments": [
            {"type": "claim", "text": "unsupported", "citation_ids": ["c99"], "quote": "nope"}
        ],
    }
    out = cva.run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.GROUNDING_FAILURE


def test_falls_back_to_lexical_when_no_gateway_configured(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(cva, "_ENTAILMENT_FN", None)
    state = {
        "retrieval": [CHUNK],
        "candidate_segments": [
            {
                "type": "claim",
                "text": "record respiratory rate at presentation",
                "citation_ids": ["c1"],
                "quote": "Record respiratory rate at presentation",
            }
        ],
    }
    out = cva.run(state)  # type: ignore[arg-type]
    assert out["grounding_report"]["action"] == "release"
