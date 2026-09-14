"""No-fabrication validator for auto-generated narratives (ARCH §15.1 step 5;
PRD-061; DEVIATIONS #66)."""

from __future__ import annotations

from app.eval.question_gen.validate import record_value_vocabulary, validate_narrative

RECORD = {
    "record_id": "r1",
    "mrn": "MRN-1",
    "sex": "male",
    "encounter": {
        "gestational_age_weeks": 34.0,
        "birth_weight_g": 1800.0,
        "day_of_life": 3,
        "presenting_complaint": "grunting",
    },
    "problems": ["lethargy"],
    "examination_findings": [{"name": "hypothermia", "present": True}],
    "vitals": [{"temperature_c": 35.2, "resp_rate_bpm": 68.0}],
}


def test_record_value_vocabulary_excludes_identity_fields() -> None:
    vocab = record_value_vocabulary(RECORD)
    assert "r1" not in vocab
    assert "mrn-1" not in vocab and "mrn" not in vocab  # from the mrn VALUE, not the key


def test_record_value_vocabulary_includes_clinical_values() -> None:
    vocab = record_value_vocabulary(RECORD)
    # "35.2" tokenizes to "35" + "2" (the analyzer splits on "." -- not a bug,
    # the two pieces still individually ground "35" and "2" in a narrative).
    for word in ("male", "34", "1800", "grunting", "lethargy", "hypothermia", "35", "68"):
        assert word in vocab, word


def test_narrative_grounded_in_record_passes() -> None:
    q = (
        "What does the guideline recommend for a male newborn at 34 weeks "
        "gestation presenting with grunting, lethargy, and hypothermia?"
    )
    report = validate_narrative(q, RECORD)
    assert report.ok, report.notes
    assert "grunting" in report.mapped_entities


def test_narrative_with_fabricated_finding_fails() -> None:
    q = (
        "What does the guideline recommend for a newborn presenting with "
        "grunting and a bulging fontanelle?"  # "bulging fontanelle" not in the record
    )
    report = validate_narrative(q, RECORD)
    assert not report.ok
    assert "bulging" in report.unmapped_entities
    assert "fontanelle" in report.unmapped_entities


def test_framing_words_never_flagged_as_unmapped() -> None:
    q = "What does the guideline recommend for an infant presenting with grunting?"
    report = validate_narrative(q, RECORD)
    assert report.ok
    assert "what" not in report.unmapped_entities
    assert "guideline" not in report.unmapped_entities


def test_allowed_topic_terms_permit_the_guideline_topic() -> None:
    q = (
        "What does the guideline on serious bacterial infection recommend "
        "for an infant presenting with grunting?"
    )
    without_topic = validate_narrative(q, RECORD)
    assert not without_topic.ok  # "serious", "bacterial", "infection" not in the record

    with_topic = validate_narrative(q, RECORD, allowed_topic_terms=["serious bacterial infection"])
    assert with_topic.ok, with_topic.notes


def test_empty_narrative_is_vacuously_ok() -> None:
    report = validate_narrative("", RECORD)
    assert report.ok
