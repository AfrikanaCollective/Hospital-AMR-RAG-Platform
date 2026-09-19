"""Map a `criteria` chunk's extracted `meta.criteria[]` onto patient-record
feature paths, and evaluate them (SCOPE-2.1; ARCH §9.2, §10.2, §6 rule 4).

`app.ingestion.chunking._extract_criteria` produces free-text field labels
straight from a PDF table cell (e.g. "heart rate", "Temp", "SpO2") — not
`PatientRecord` field paths. `_CRITERIA_FIELD_SYNONYMS` is the curated,
never-inferred mapping from that free text to
`app.records.access.extract_features` output paths, the same
curated-only-never-invented pattern already used for retrieval query
expansion (`app.retrieval.hybrid._ABBREVIATIONS`, DEVIATIONS.md #55) —
extended here for criteria matching (DEVIATIONS.md #71). An unmapped field
label evaluates as `matched=None` ("uncertain", not a guessed pass/fail),
which is exactly the stage-classifier's escalation signal (ARCH §9.2 rule 4).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any

# Ordered longest-key-first so e.g. "birth weight" wins over "weight".
_CRITERIA_FIELD_SYNONYMS: dict[str, str] = {
    "gestational age": "encounter.gestational_age_weeks",
    "birth weight": "encounter.birth_weight_g",
    "day of life": "encounter.day_of_life",
    "capillary refill": "vitals.capillary_refill_seconds",
    "oxygen saturation": "vitals.spo2_percent",
    "respiratory rate": "vitals.resp_rate_bpm",
    "heart rate": "vitals.heart_rate_bpm",
    "mean bp": "vitals.mean_bp_mmhg",
    "mean arterial pressure": "vitals.mean_bp_mmhg",
    "systolic": "vitals.systolic_bp_mmhg",
    "diastolic": "vitals.diastolic_bp_mmhg",
    "temperature": "vitals.temperature_c",
    "weight": "vitals.weight_g",
    "spo2": "vitals.spo2_percent",
    "hr": "vitals.heart_rate_bpm",
    "rr": "vitals.resp_rate_bpm",
    "temp": "vitals.temperature_c",
}
_SYNONYM_KEYS_BY_LENGTH = sorted(_CRITERIA_FIELD_SYNONYMS, key=len, reverse=True)

# Repeating groups in app.records.access.extract_features's "latest-projected"
# paths (e.g. "vitals.heart_rate_bpm") correspond to indexed field_index keys
# (e.g. "vitals.0.heart_rate_bpm", "vitals.1.heart_rate_bpm", ...) — this is
# the concept-level presence check missing_info_agent uses so it can work
# from field_index alone, without decrypting (ARCH §4.2).
_LIST_FIELD_PREFIXES = (
    "vitals",
    "labs",
    "medications",
    "examination_findings",
    "interventions",
    "maternal_risk_factors",
)

_OPERATORS: dict[str, Any] = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "=": operator.eq,
}


def field_present_in_index(field_index: dict[str, bool], concept_path: str) -> bool:
    """Is `concept_path` (a `extract_features`-style "latest" path) present in
    a raw `field_index` (names + null-ness, indexed for repeating groups)?
    A repeating-group concept (e.g. "vitals.heart_rate_bpm") is present if
    ANY entry in that group recorded it."""
    if concept_path in field_index:
        return bool(field_index[concept_path])
    prefix, _, leaf = concept_path.partition(".")
    if prefix not in _LIST_FIELD_PREFIXES or not leaf:
        return False
    return any(
        k.startswith(f"{prefix}.") and k.endswith(f".{leaf}") and v for k, v in field_index.items()
    )


def map_criterion_field(field_text: str) -> str | None:
    """Curated, never-inferred mapping only — returns None (uncertain) for
    anything not in `_CRITERIA_FIELD_SYNONYMS`."""
    lowered = field_text.strip().lower()
    for key in _SYNONYM_KEYS_BY_LENGTH:
        if key in lowered:
            return _CRITERIA_FIELD_SYNONYMS[key]
    return None


@dataclass(frozen=True)
class CriterionMatch:
    criterion: dict
    feature_path: str | None
    feature_value: float | str | None
    matched: bool | None  # None = uncertain (unmapped field or missing feature)


def evaluate_criteria(criteria: list[dict], features: dict[str, Any]) -> list[CriterionMatch]:
    """Evaluate each `{field, operator, value, unit}` criterion against
    `patient_features` (ARCH §9.2). Never guesses: an unmapped field or an
    absent feature value yields `matched=None`, never a fabricated pass/fail."""
    results: list[CriterionMatch] = []
    for criterion in criteria:
        path = map_criterion_field(criterion.get("field", ""))
        if path is None or path not in features:
            results.append(CriterionMatch(criterion, path, None, None))
            continue
        value = features[path]
        op_fn = _OPERATORS.get(criterion.get("operator", ""))
        if op_fn is None or not isinstance(value, int | float):
            results.append(CriterionMatch(criterion, path, value, None))
            continue
        matched = bool(op_fn(value, criterion["value"]))
        results.append(CriterionMatch(criterion, path, value, matched))
    return results
