"""Auto-generated hypothetical question narrative generation (ARCH §15.1
steps 3-6; PRD-060, PRD-061; DEVIATIONS #66-67).

A dedicated fake `_ChatGateway` stands in for `LLMGateway` — distinct from
the production `app.llm.stub.stub_chat`, which deliberately never generates
real content (a safety property for the production answer path, not
something question-gen tests can use to produce narrative text)."""

from __future__ import annotations

import pytest

from app.eval.question_gen.generate import (
    QuestionGenerationFailed,
    _field_subset_lines,
    _humanize,
    _is_scope1_framed,
    generate_question,
)
from app.schemas.enums import ExpectedOutcome, Provenance

RECORD = {
    "record_id": "r1",
    "mrn": "MRN-1",
    "sex": "male",
    "encounter": {
        "gestational_age_weeks": 34.0,
        "day_of_life": 3,
        "presenting_complaint": "grunting",
    },
    "problems": ["lethargy"],
}


class _FakeChatResult:
    def __init__(self, text: str, model_id: str = "fake-model") -> None:
        self.text = text
        self.model_id = model_id
        self.usage: dict = {}


class _FakeGateway:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, *, system: str, messages: list[dict], **params: object) -> _FakeChatResult:
        self.calls.append({"system": system, "messages": messages, "params": params})
        text = self._responses.pop(0) if self._responses else self._responses[-1]
        return _FakeChatResult(text)


GOOD_QUESTION = (
    "What does the guideline recommend for a male newborn at 34 weeks "
    "gestation presenting with grunting and lethargy?"
)


def test_generate_question_success_on_first_attempt() -> None:
    gw = _FakeGateway([GOOD_QUESTION])
    result = generate_question(RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw)
    assert result["text"] == GOOD_QUESTION
    assert result["provenance"] == Provenance.AUTO_GENERATED
    assert result["expected_outcome"] == ExpectedOutcome.WELL_SUPPORTED
    assert result["source_record_id"] == "r1"
    assert result["generator_meta"]["attempt"] == 0
    assert result["generator_meta"]["template_version"] == "v1"
    assert result["generator_meta"]["validator_report"]["ok"] is True
    assert len(gw.calls) == 1


def test_generate_question_retries_after_a_directive_framed_attempt() -> None:
    bad = "What treatment should this infant receive for grunting and lethargy?"
    gw = _FakeGateway([bad, GOOD_QUESTION])
    result = generate_question(RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw, max_retries=2)
    assert result["text"] == GOOD_QUESTION
    assert result["generator_meta"]["attempt"] == 1
    assert len(gw.calls) == 2


def test_generate_question_retries_after_an_unmapped_entity() -> None:
    fabricated = (
        "What does the guideline recommend for a newborn presenting with a bulging fontanelle?"
    )
    gw = _FakeGateway([fabricated, GOOD_QUESTION])
    result = generate_question(RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw, max_retries=2)
    assert result["text"] == GOOD_QUESTION


def test_generate_question_raises_after_exhausting_retries() -> None:
    bad = "What treatment should this infant receive?"
    gw = _FakeGateway([bad, bad, bad])
    with pytest.raises(QuestionGenerationFailed):
        generate_question(RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw, max_retries=2)
    assert len(gw.calls) == 3  # initial + 2 retries


def test_target_guideline_ref_set_for_well_supported() -> None:
    gw = _FakeGateway([GOOD_QUESTION])
    result = generate_question(
        RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw, target_guideline_topic="neonatal sepsis"
    )
    assert result["target_guideline_ref"] == {"topic": "neonatal sepsis"}


def test_target_guideline_ref_none_for_no_guideline_expected_even_with_topic() -> None:
    gw = _FakeGateway([GOOD_QUESTION])
    result = generate_question(
        RECORD,
        ExpectedOutcome.NO_GUIDELINE_EXPECTED,
        gateway=gw,
        target_guideline_topic="something not covered",
    )
    assert result["target_guideline_ref"] is None


def test_topic_terms_extend_the_validator_allowed_vocabulary() -> None:
    q = (
        "What does the guideline on neonatal sepsis recommend for a newborn "
        "presenting with grunting?"
    )
    gw = _FakeGateway([q])
    result = generate_question(
        RECORD, ExpectedOutcome.WELL_SUPPORTED, gateway=gw, target_guideline_topic="neonatal sepsis"
    )
    assert result["generator_meta"]["validator_report"]["ok"] is True


# ── _field_subset_lines ──────────────────────────────────────────────────────


def test_field_subset_lines_includes_present_fields() -> None:
    lines = _field_subset_lines(RECORD)
    assert "male" in lines
    assert "34.0" in lines
    assert "grunting" in lines
    assert "lethargy" in lines


def test_field_subset_lines_never_states_absent_fields() -> None:
    lines = _field_subset_lines(RECORD)
    assert "allerg" not in lines.lower()  # no allergies field present -> not mentioned at all
    assert "medication" not in lines.lower()


def test_field_subset_lines_handles_empty_record() -> None:
    lines = _field_subset_lines({"record_id": "r2", "mrn": "MRN-2"})
    assert "no structured clinical fields" in lines


def test_field_subset_lines_never_includes_medications_or_interventions() -> None:
    """DEVIATIONS.md #155 (operator instruction): a generated question must
    never be able to mention a medication or intervention, since seeing one
    let a real gateway model infer an unstated diagnosis (DEVIATIONS #115)."""
    record = {
        **RECORD,
        "medications": [{"name": "gentamicin", "active": True}],
        "interventions": [{"name": "cpap", "active": True}],
    }
    lines = _field_subset_lines(record)
    assert "gentamicin" not in lines.lower()
    assert "cpap" not in lines.lower()
    assert "medication" not in lines.lower()
    assert "intervention" not in lines.lower()


def test_field_subset_lines_humanizes_underscored_finding_names() -> None:
    """DEVIATIONS.md #155: an EAV-source member name like "difficulty_feeding"
    is an internal identifier, not prose -- must read as "difficulty feeding"
    in the prompt so the model doesn't reproduce the underscore verbatim."""
    record = {**RECORD, "examination_findings": [{"name": "difficulty_feeding", "present": True}]}
    lines = _field_subset_lines(record)
    assert "difficulty feeding" in lines
    assert "difficulty_feeding" not in lines


def test_humanize_replaces_underscores_with_spaces() -> None:
    assert _humanize("difficulty_feeding") == "difficulty feeding"
    assert _humanize("grunting") == "grunting"


# ── _is_scope1_framed ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "What does the guideline recommend for an infant presenting with grunting?",
        "What does the guideline say for a newborn presenting with lethargy and hypothermia?",
    ],
)
def test_is_scope1_framed_accepts_guideline_lookup_questions(text: str) -> None:
    assert _is_scope1_framed(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "What treatment should this infant receive for grunting?",
        "Should this newborn be started on antibiotics given the lethargy?",
        "What is the next step for this patient presenting with grunting?",
        "What does the guideline recommend for grunting",  # no question mark
        "This infant has grunting and lethargy.",  # no "guideline" at all
        "You should administer antibiotics to this patient with grunting.",
    ],
)
def test_is_scope1_framed_rejects_directive_or_malformed_questions(text: str) -> None:
    assert _is_scope1_framed(text) is False
