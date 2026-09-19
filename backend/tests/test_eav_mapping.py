"""EAV pivot + declarative mapping (ARCH-039; DEVIATIONS #34)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.eav import MappingSpec, apply_mapping, build_records, load_wide
from app.schemas.record import DEIDENTIFIED_PROVENANCE

REPO = Path(__file__).resolve().parents[2]
REAL_DIR = REPO / "data/patient_records/deidentified/newborn_nbu_2021"

TINY_CSV = """"key","field_name","field_value","context"
7,"age_days","2","demographics"
7,"birth_weight","1.2","demographics"
7,"gestational_age","28","demographics"
7,"sex","Male","demographics"
7,"weight_now","1.3","demographics"
7,"admission_date_time","2021-03-01 06:00:00","encounter_details"
7,"care_setting","NBU","encounter_details"
7,"triage_category","None","encounter_details"
7,"heart_rate","150","vitals"
7,"temparature","36.6","vitals"
7,"capillary_refill","2","vitals"
7,"apnoea","TRUE","history_examination"
7,"grunting","FALSE","history_examination"
7,"oxygen","TRUE","interventions"
7,"gentamicin","TRUE","medication"
7,"penicillin","FALSE","medication"
7,"maternal_infection","TRUE","maternal_risk_factors"
7,"prom","NA","maternal_risk_factors"
8,"age_days","0","demographics"
8,"sex","Female","demographics"
"""

TINY_MAPPING = """
dataset_id: tiny
provenance: deidentified-anonymised
schema_version: "1.3.0"
identity: { record_id: "{key}", mrn: "DEID-{key}" }
vitals_recorded_at_from: admission_date_time
fields:
  age_days:            { target: encounter.day_of_life, transform: to_int }
  birth_weight:        { target: encounter.birth_weight_g, transform: kg_to_g }
  gestational_age:     { target: encounter.gestational_age_weeks, transform: to_float }
  sex:                 { target: sex, transform: sex_norm }
  weight_now:          { target: vitals.0.weight_g, transform: kg_to_g }
  admission_date_time: { target: encounter.admitted_at, transform: parse_datetime }
  care_setting:        { target: encounter.care_setting, transform: identity }
  triage_category:     { target: encounter.triage_category, transform: none_literal_to_null }
  heart_rate:          { target: vitals.0.heart_rate_bpm, transform: to_float }
  temparature:         { target: vitals.0.temperature_c, transform: to_float }
  capillary_refill:    { target: vitals.0.capillary_refill_seconds, transform: to_float }
list_targets:
  examination_findings:
    target: examination_findings
    present_key: present
    recorded_at_from: admission_date_time
    ts_key: recorded_at
    members: [apnoea, grunting]
  interventions:
    target: interventions
    active_key: active
    started_at_from: admission_date_time
    ts_key: started_at
    members: [oxygen]
  medications:
    target: medications
    active_key: active
    started_at_from: admission_date_time
    ts_key: started_at
    members: [gentamicin, penicillin]
  maternal_risk_factors:
    target: maternal_risk_factors
    present_key: present
    recorded_at_from: admission_date_time
    ts_key: recorded_at
    members: [maternal_infection, prom]
derived:
  date_of_birth: { rule: admitted_minus_days }
defaults:
  consent_flags: { deidentified: true }
"""


@pytest.fixture
def tiny(tmp_path: Path) -> tuple[Path, MappingSpec]:
    csv_p = tmp_path / "tiny.csv"
    csv_p.write_text(TINY_CSV, encoding="utf-8")
    map_p = tmp_path / "map.yaml"
    map_p.write_text(TINY_MAPPING, encoding="utf-8")
    return csv_p, MappingSpec.from_yaml(map_p)


def test_pivot_is_one_wide_row_per_key(tiny: tuple[Path, MappingSpec]) -> None:
    csv_p, _ = tiny
    wide = dict(load_wide(csv_p))
    assert set(wide) == {"7", "8"}
    assert wide["7"]["birth_weight"] == "1.2"
    assert wide["8"] == {"age_days": "0", "sex": "Female"}


def test_transforms_and_derived(tiny: tuple[Path, MappingSpec]) -> None:
    csv_p, spec = tiny
    wide = dict(load_wide(csv_p))
    d = apply_mapping("7", wide["7"], spec)
    assert d["record_id"] == "7" and d["mrn"] == "DEID-7"
    assert d["sex"] == "male"
    assert d["encounter"]["birth_weight_g"] == 1200.0  # 1.2 kg -> g
    assert d["encounter"]["gestational_age_weeks"] == 28.0
    assert d["encounter"]["day_of_life"] == 2
    assert d["encounter"].get("triage_category") is None  # "None" literal -> absent/null
    assert d["encounter"]["admitted_at"].isoformat().startswith("2021-03-01T06:00:00")
    assert d["vitals"][0]["weight_g"] == 1300.0
    assert d["vitals"][0]["capillary_refill_seconds"] == 2.0
    assert d["date_of_birth"] == "2021-02-27"  # admitted - 2 days
    assert d["consent_flags"] == {"deidentified": True}


def test_list_families_preserve_present_absent(tiny: tuple[Path, MappingSpec]) -> None:
    csv_p, spec = tiny
    wide = dict(load_wide(csv_p))
    d = apply_mapping("7", wide["7"], spec)
    findings = {f["name"]: f["present"] for f in d["examination_findings"]}
    assert findings == {"apnoea": True, "grunting": False}
    assert [m["name"] for m in d["medications"]] == ["gentamicin", "penicillin"]
    assert {m["name"]: m["active"] for m in d["medications"]} == {
        "gentamicin": True,
        "penicillin": False,
    }
    assert d["interventions"] == [
        {"name": "oxygen", "active": True, "started_at": d["interventions"][0]["started_at"]}
    ]


def test_na_sentinel_means_not_assessed_distinct_from_false(tiny: tuple[Path, MappingSpec]) -> None:
    """DEVIATIONS #138/#139: FALSE = assessed and absent (a real list item);
    NA (or a fully missing row) = never assessed (no list item at all)."""
    csv_p, spec = tiny
    wide = dict(load_wide(csv_p))
    d = apply_mapping("7", wide["7"], spec)
    names = {f["name"] for f in d["maternal_risk_factors"]}
    assert names == {"maternal_infection"}  # "prom" was "NA" -> not assessed, no item
    assert {f["name"]: f["present"] for f in d["maternal_risk_factors"]} == {
        "maternal_infection": True
    }


def test_build_records_validates_against_schema(tiny: tuple[Path, MappingSpec]) -> None:
    csv_p, spec = tiny
    recs = list(build_records(csv_p, spec))
    assert len(recs) == 2
    assert recs[0].given_name is None and recs[0].family_name is None
    assert recs[0].dataset_provenance == DEIDENTIFIED_PROVENANCE
    assert recs[0].schema_version == "1.3.0"


def test_medication_and_intervention_started_at_equals_admitted_at(
    tiny: tuple[Path, MappingSpec],
) -> None:
    """DEVIATIONS #39: every mapped med/intervention starts at encounter.admitted_at
    (this dataset has no per-item start time); stopped_at stays null."""
    csv_p, spec = tiny
    rec = next(iter(build_records(csv_p, spec)))
    adm = rec.encounter.admitted_at
    assert adm is not None
    assert rec.medications and rec.interventions
    for m in rec.medications:
        assert m.started_at == adm
        assert m.stopped_at is None
    for iv in rec.interventions:
        assert iv.started_at == adm
        assert iv.stopped_at is None


@pytest.mark.skipif(
    not (REAL_DIR / "rag_dataset.csv").exists(),
    reason="real de-identified dataset not present (expected in CI)",
)
def test_real_dataset_maps_cleanly() -> None:
    spec = MappingSpec.from_yaml(REAL_DIR / "field_mapping.yaml")
    recs = list(build_records(REAL_DIR / "rag_dataset.csv", spec, limit=50))
    assert len(recs) == 50
    assert all(r.mrn.startswith("DEID-") for r in recs)
    assert all(r.given_name is None for r in recs)
    assert any(r.encounter.gestational_age_weeks for r in recs)
    assert any(r.vitals and r.vitals[0].capillary_refill_seconds for r in recs)
    # DEVIATIONS #39: med/intervention started_at == encounter.admitted_at; stopped_at null
    for r in recs:
        for item in [*r.medications, *r.interventions]:
            if r.encounter.admitted_at is not None:
                assert item.started_at == r.encounter.admitted_at
            assert item.stopped_at is None
