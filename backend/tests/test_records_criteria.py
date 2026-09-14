"""Criteria field mapping + evaluation (SCOPE-2.1; ARCH §9.2; DEVIATIONS.md #71)."""

from __future__ import annotations

from app.records.criteria import evaluate_criteria, map_criterion_field


def test_curated_synonyms_map() -> None:
    assert map_criterion_field("Heart Rate") == "vitals.heart_rate_bpm"
    assert map_criterion_field("birth weight") == "encounter.birth_weight_g"
    assert map_criterion_field("SpO2") == "vitals.spo2_percent"


def test_longest_match_wins_over_shorter_substring() -> None:
    assert map_criterion_field("birth weight in grams") == "encounter.birth_weight_g"


def test_unmapped_field_returns_none() -> None:
    assert map_criterion_field("some unrecognised lab") is None


def test_evaluate_criteria_pass_fail_and_uncertain() -> None:
    criteria = [
        {"field": "heart rate", "operator": ">", "value": 160.0, "unit": None},
        {"field": "temperature", "operator": "<", "value": 36.0, "unit": None},
        {"field": "unrecognised marker", "operator": ">", "value": 5.0, "unit": None},
    ]
    features = {"vitals.heart_rate_bpm": 180.0, "vitals.temperature_c": 37.0}
    results = evaluate_criteria(criteria, features)
    assert results[0].matched is True
    assert results[1].matched is False
    assert results[2].matched is None  # unmapped field: uncertain, never guessed


def test_missing_feature_is_uncertain_not_a_guess() -> None:
    criteria = [{"field": "gestational age", "operator": "<", "value": 34.0, "unit": "weeks"}]
    results = evaluate_criteria(criteria, {})
    assert results[0].matched is None
