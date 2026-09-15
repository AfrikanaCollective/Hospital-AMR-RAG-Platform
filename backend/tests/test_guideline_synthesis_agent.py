"""Guideline-synthesis agent (SCOPE-1; ARCH §8.2, §9.1)."""

from __future__ import annotations

import json

import app.agents.guideline_synthesis_agent as gsa
from app.schemas.enums import EscalationTrigger, ObservedOutcome, SegmentType

CHUNK = {
    "chunk_id": "ch1",
    "text": "Record respiratory rate at presentation for every neonate.",
    "document_title": "Newborn Care Guideline",
    "version_label": "2021",
    "section_number": "3.2",
    "page_start": 5,
    "page_end": 5,
}


def _valid_response() -> str:
    return json.dumps(
        [
            {"type": "framing", "text": "Per the retrieved guideline:"},
            {
                "type": "claim",
                "text": "Guideline X recommends recording respiratory rate at presentation.",
                "citation_ids": ["c1"],
                "quote": "Record respiratory rate at presentation",
            },
        ]
    )


def test_default_chat_fn_records_model_id_on_state(monkeypatch) -> None:  # noqa: ANN001
    """The real (non-`_CHAT_FN`-overridden) path must record which model
    answered, for the "answer" audit event (ARCH-035, DEVIATIONS.md #91)."""

    class _FakeResult:
        text = _valid_response()
        model_id = "stub-model-v7"

    class _FakeGateway:
        def chat(self, **kwargs):  # noqa: ANN003, ARG002
            return _FakeResult()

    monkeypatch.setattr(gsa, "_CHAT_FN", None)
    monkeypatch.setattr(gsa, "LLMGateway", _FakeGateway)
    state = {
        "query": "what does the guideline say?",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert out["model_id"] == "stub-model-v7"


def test_essentially_empty_retrieval_returns_no_guideline_without_model_call(monkeypatch) -> None:  # noqa: ANN001
    calls = []
    monkeypatch.setattr(gsa, "_CHAT_FN", lambda prompt: calls.append(prompt) or "[]")  # noqa: ARG005
    state = {
        "query": "what does the guideline say about scurvy?",
        "retrieval": [],
        "retrieval_confidence": {
            "essentially_empty": True,
            "low_confidence": True,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert out["observed_outcome"] == ObservedOutcome.NO_GUIDELINE
    assert out["candidate_segments"][0]["text"] == gsa.NO_GUIDELINE_TEXT
    assert calls == []  # no model call was made


def test_conflicting_sources_escalates_without_model_call(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        gsa,
        "_CHAT_FN",
        lambda prompt: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [{"a": 1}],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.CONFLICTING_SOURCES


def test_low_confidence_escalates_without_model_call(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        gsa,
        "_CHAT_FN",
        lambda prompt: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": True,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.LOW_CONFIDENCE


def test_good_retrieval_calls_model_and_parses_segments(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(gsa, "_CHAT_FN", lambda prompt: _valid_response())
    state = {
        "query": "what does the guideline recommend for a neonate presenting with fever?",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert "escalation" not in out
    assert out["candidate_segments"][1]["type"] == SegmentType.CLAIM


def test_malformed_output_retries_then_escalates(monkeypatch) -> None:  # noqa: ANN001
    calls = {"n": 0}

    def _chat(prompt: str) -> str:  # noqa: ARG001
        calls["n"] += 1
        return "not json"

    monkeypatch.setattr(gsa, "_CHAT_FN", _chat)
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert calls["n"] == 3  # two retries (DEVIATIONS.md #111: _MAX_ATTEMPTS raised 2 -> 3)
    assert out["escalation"]["trigger_code"] == EscalationTrigger.GROUNDING_FAILURE


def test_second_attempt_succeeding_recovers(monkeypatch) -> None:  # noqa: ANN001
    calls = {"n": 0}

    def _chat(prompt: str) -> str:  # noqa: ARG001
        calls["n"] += 1
        return "not json" if calls["n"] == 1 else _valid_response()

    monkeypatch.setattr(gsa, "_CHAT_FN", _chat)
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert "escalation" not in out
    assert calls["n"] == 2


def test_third_attempt_succeeding_recovers(monkeypatch) -> None:  # noqa: ANN001
    """DEVIATIONS.md #111: _MAX_ATTEMPTS raised 2 -> 3 after a real model was
    observed ignoring the JSON format on the first retry too — the second
    retry must still get a chance."""
    calls = {"n": 0}

    def _chat(prompt: str) -> str:  # noqa: ARG001
        calls["n"] += 1
        return "not json" if calls["n"] < 3 else _valid_response()

    monkeypatch.setattr(gsa, "_CHAT_FN", _chat)
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert "escalation" not in out
    assert calls["n"] == 3


def test_prose_with_inline_citation_markers_is_rejected_not_parsed(monkeypatch) -> None:  # noqa: ANN001
    """DEVIATIONS.md #111: reproduces the exact real-world failure shape —
    the model ignoring the JSON schema entirely and writing flattened prose
    with inline `[c1]`-style citation markers instead. This must never be
    treated as valid output (there is no verbatim quote to machine-verify
    against a source, only a paraphrase with a bracket) — it should fail to
    parse on every attempt and escalate, same as any other malformed output."""
    prose = (
        "The guideline addresses the management of small and sick newborns "
        "presenting with specific danger signs such as apnoea, fever, and low "
        "birth weight. Per [source], small and sick newborns are adequately "
        "monitored, appropriately reassessed and receive supportive care "
        "according to MoH guidelines.[c1]"
    )
    monkeypatch.setattr(gsa, "_CHAT_FN", lambda prompt: prose)  # noqa: ARG005
    state = {
        "query": "x",
        "retrieval": [CHUNK],
        "retrieval_confidence": {
            "essentially_empty": False,
            "low_confidence": False,
            "conflicts": [],
        },
    }
    out = gsa.run(state)  # type: ignore[arg-type]
    assert out["escalation"]["trigger_code"] == EscalationTrigger.GROUNDING_FAILURE
