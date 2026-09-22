"""Diversity filter (ARCH §15.1 step 7; DEVIATIONS.md #67, #113, #187, #188)."""

from __future__ import annotations

from app.eval.question_gen.diversity import (
    is_clinically_near_duplicate,
    jaccard_similarity,
    vitals_within_tolerance,
)


def test_jaccard_similarity_identical_sets_is_one() -> None:
    assert jaccard_similarity(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0


def test_jaccard_similarity_disjoint_sets_is_zero() -> None:
    assert jaccard_similarity(frozenset({"a"}), frozenset({"b"})) == 0.0


def test_jaccard_similarity_partial_overlap() -> None:
    # {a,b,c} ∩ {a,b} = {a,b} (2); {a,b,c} ∪ {a,b} = {a,b,c} (3) -> 2/3
    assert jaccard_similarity(frozenset({"a", "b", "c"}), frozenset({"a", "b"})) == 2 / 3


def test_jaccard_similarity_both_empty_is_one() -> None:
    """Vacuously "identical" -- no real signal either way, matches
    `vitals_within_tolerance`'s own empty-overlap convention."""
    assert jaccard_similarity(frozenset(), frozenset()) == 1.0


def test_vitals_within_tolerance_true_for_close_values() -> None:
    assert vitals_within_tolerance({"heart_rate_bpm": 140.0}, {"heart_rate_bpm": 148.0})


def test_vitals_within_tolerance_false_for_a_field_outside_its_band() -> None:
    # spo2_percent tolerance is 5.0 -- 93 vs 70 is a 23-point gap.
    assert not vitals_within_tolerance({"spo2_percent": 93.0}, {"spo2_percent": 70.0})


def test_vitals_within_tolerance_ignores_fields_not_shared() -> None:
    assert vitals_within_tolerance({"heart_rate_bpm": 140.0}, {"spo2_percent": 93.0})


def test_vitals_within_tolerance_true_when_nothing_shared_at_all() -> None:
    assert vitals_within_tolerance({}, {})


# ── is_clinically_near_duplicate (DEVIATIONS.md #188) ────────────────────────

_RECORD_A = {
    "sex": "male",
    "encounter": {"gestational_age_weeks": 32, "birth_weight_g": 1700, "day_of_life": 1},
    "examination_findings": [
        {"name": "crackles", "present": True},
        {"name": "grunting", "present": True},
        {"name": "difficulty_feeding", "present": False},
    ],
    "vitals": [{"resp_rate_bpm": 58.0, "spo2_percent": 93.0}],
}

# Same demographics as A, but materially different clinical presentation
# (severe hypoxia, SpO2 70% vs 93%; different findings) -- DEVIATIONS #187's
# real, live-verified false-positive case for the two prior embedding-based
# attempts. Must NOT be flagged as a near-duplicate of A.
_RECORD_B_SAME_DEMOGRAPHICS_DIFFERENT_PRESENTATION = {
    "sex": "male",
    "encounter": {"gestational_age_weeks": 32, "birth_weight_g": 1700, "day_of_life": 1},
    "examination_findings": [
        {"name": "difficulty_feeding", "present": True},
        {"name": "floppy", "present": True},
        {"name": "grunting", "present": True},
    ],
    "vitals": [{"resp_rate_bpm": 82.0, "spo2_percent": 70.0}],
}

# Genuinely near-identical to A: same findings, vitals within tolerance.
_RECORD_C_GENUINE_NEAR_DUPLICATE_OF_A = {
    "sex": "female",  # demographics differ too -- shouldn't matter, only clinical content does
    "encounter": {"gestational_age_weeks": 40, "birth_weight_g": 3200, "day_of_life": 4},
    "examination_findings": [
        {"name": "crackles", "present": True},
        {"name": "grunting", "present": True},
    ],
    "vitals": [{"resp_rate_bpm": 62.0, "spo2_percent": 90.0}],  # within tolerance of A's 58/93
}


def test_not_a_near_duplicate_when_demographics_match_but_presentation_differs() -> None:
    assert not is_clinically_near_duplicate(
        _RECORD_B_SAME_DEMOGRAPHICS_DIFFERENT_PRESENTATION,
        [_RECORD_A],
        findings_jaccard_threshold=0.8,
    )


def test_is_a_near_duplicate_when_findings_and_vitals_both_closely_match() -> None:
    assert is_clinically_near_duplicate(
        _RECORD_C_GENUINE_NEAR_DUPLICATE_OF_A, [_RECORD_A], findings_jaccard_threshold=0.8
    )


def test_not_a_near_duplicate_when_findings_match_but_vitals_dont() -> None:
    """Jaccard alone is not sufficient -- matching findings with vitals
    outside tolerance must not reject (both signals must hold, DEVIATIONS
    #188)."""
    candidate = {
        "examination_findings": [
            {"name": "crackles", "present": True},
            {"name": "grunting", "present": True},
        ],
        "vitals": [{"resp_rate_bpm": 58.0, "spo2_percent": 99.0}],  # spo2 far outside tolerance
    }
    assert not is_clinically_near_duplicate(candidate, [_RECORD_A], findings_jaccard_threshold=0.8)


def test_not_a_near_duplicate_when_vitals_match_but_findings_dont() -> None:
    candidate = {
        "examination_findings": [{"name": "apnoea", "present": True}],
        "vitals": [{"resp_rate_bpm": 58.0, "spo2_percent": 93.0}],  # vitals identical to A
    }
    assert not is_clinically_near_duplicate(candidate, [_RECORD_A], findings_jaccard_threshold=0.8)


def test_empty_candidate_is_never_a_near_duplicate() -> None:
    """A record with no structured clinical content at all has no real
    signal to compare -- never flagged, even against an equally-empty
    accepted record."""
    assert not is_clinically_near_duplicate({}, [{}], findings_jaccard_threshold=0.8)


def test_empty_accepted_pool_is_never_a_match() -> None:
    assert not is_clinically_near_duplicate(_RECORD_A, [], findings_jaccard_threshold=0.8)
