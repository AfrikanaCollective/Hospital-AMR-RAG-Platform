"""Deterministic ablation-study narrative construction (DEVIATIONS.md #156)."""

from __future__ import annotations

from app.eval.question_gen.deterministic import build_deterministic_narrative

RECORD = {
    "record_id": "SYNREC-TEST",
    "mrn": "SYN-TEST",
    "sex": "female",
    "encounter": {
        "gestational_age_weeks": 33.0,
        "birth_weight_g": 1800.0,
        "day_of_life": 2,
        "care_setting": "NBU",
        "presenting_complaint": "poor feeding",
    },
    "examination_findings": [
        {"name": "grunting", "present": True},
        {"name": "difficulty_feeding", "present": True},
        {"name": "convulsions", "present": False},
        {"name": "floppy", "present": False},
    ],
    "maternal_risk_factors": [
        {"name": "maternal_infection", "present": True},
        {"name": "prom", "present": False},
    ],
    "vitals": [{"heart_rate_bpm": 190.0, "resp_rate_bpm": 65.0}],
    "medications": [{"name": "gentamicin", "active": True}],
    "interventions": [{"name": "cpap", "active": True}],
}


def test_includes_topic_line() -> None:
    text = build_deterministic_narrative(RECORD, topic="antibiotics or infection")
    assert text.startswith(
        "What does the guideline recommend about antibiotics or infection "
        "based only on the content provided below:"
    )


def test_includes_demographic_fields_present() -> None:
    text = build_deterministic_narrative(RECORD, topic="x")
    assert "female" in text
    assert "is 2 days old" in text
    assert "born at 33.0 weeks gestation" in text
    assert "birth weight of 1800.0 g" in text
    assert "currently in NBU" in text
    assert "presenting with poor feeding" in text


def test_omits_absent_demographic_fields_never_states_them() -> None:
    record = {"record_id": "r", "mrn": "m", "sex": "male", "encounter": {}}
    text = build_deterministic_narrative(record, topic="x")
    assert "gestation" not in text
    assert "birth weight" not in text
    assert "NBU" not in text


def test_present_and_absent_exam_findings_both_appear_with_correct_phrasing() -> None:
    text = build_deterministic_narrative(RECORD, topic="x")
    assert "the patient had grunting, and difficulty feeding." in text
    assert "the patient did NOT have convulsions, and floppy." in text


def test_never_assessed_finding_is_never_mentioned_either_way() -> None:
    record = {
        **RECORD,
        "examination_findings": [{"name": "grunting", "present": True}],  # apnoea never assessed
        "maternal_risk_factors": [],
    }
    text = build_deterministic_narrative(record, topic="x")
    assert "apnoea" not in text
    assert "had grunting" in text
    assert "did NOT have" not in text  # nothing was assessed-negative here


def test_maternal_risk_factors_tri_state() -> None:
    text = build_deterministic_narrative(RECORD, topic="x")
    assert "the mother had maternal infection" in text
    assert "the mother did NOT have prom" in text


def test_vitals_included() -> None:
    text = build_deterministic_narrative(RECORD, topic="x")
    assert "heart rate (bpm) 190.0" in text
    assert "respiratory rate (bpm) 65.0" in text


def test_never_includes_medications_or_interventions() -> None:
    """DEVIATIONS.md #155's constraint applies here independently too."""
    text = build_deterministic_narrative(RECORD, topic="x")
    assert "gentamicin" not in text
    assert "cpap" not in text
    assert "medication" not in text.lower()
    assert "intervention" not in text.lower()


def test_no_findings_assessed_at_all_omits_the_assessment_section() -> None:
    record = {"record_id": "r", "mrn": "m", "sex": "male", "encounter": {}}
    text = build_deterministic_narrative(record, topic="x")
    assert "assessments at admission" not in text.lower()


def test_no_maternal_risk_factors_assessed_omits_that_clause() -> None:
    record = {"record_id": "r", "mrn": "m", "sex": "male", "encounter": {}}
    text = build_deterministic_narrative(record, topic="x")
    assert "maternal risk factors" not in text.lower()


def test_single_present_finding_has_no_trailing_and() -> None:
    record = {**RECORD, "examination_findings": [{"name": "grunting", "present": True}]}
    text = build_deterministic_narrative(record, topic="x")
    assert "the patient had grunting." in text


def test_empty_record_produces_only_the_topic_line_and_bare_sex_sentence() -> None:
    text = build_deterministic_narrative({"record_id": "r", "mrn": "m"}, topic="x")
    assert "unspecified sex" in text
    assert "assessments at admission" not in text.lower()
    assert "maternal risk factors" not in text.lower()
