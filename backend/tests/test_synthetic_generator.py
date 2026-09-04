"""Synthetic record generator: valid, clearly-synthetic, domain-aware (PRD-006, PRD-081; DEVIATIONS #30)."""

from __future__ import annotations

import pytest

from app.schemas.record import SCHEMA_VERSION, SYNTHETIC_PROVENANCE
from scripts.generate_synthetic_records import DEFAULT_DOMAIN, DOMAIN_LIBS, generate


def test_generates_requested_count_and_is_deterministic() -> None:
    a = generate(20, seed=1, sparse_fraction=0.25)
    b = generate(20, seed=1, sparse_fraction=0.25)
    assert len(a) == 20
    assert [r.record_id for r in a] == [r.record_id for r in b]


def test_every_record_marked_synthetic() -> None:
    recs = generate(30, seed=7, sparse_fraction=0.3)
    assert all(r.dataset_provenance == SYNTHETIC_PROVENANCE for r in recs)
    assert all(r.mrn.startswith("SYN-") for r in recs)
    assert all(r.schema_version == SCHEMA_VERSION for r in recs)


def test_some_records_are_sparse_for_hard_case_generation() -> None:
    recs = generate(40, seed=3, sparse_fraction=0.5)
    sparse_like = [r for r in recs if not r.labs and not r.vitals]
    assert sparse_like, "expected some sparse records (PRD-064)"


def test_real_data_heuristic_trusts_the_synthetic_marker() -> None:
    from app.ingestion.records import looks_like_real_data

    recs = generate(5, seed=1, sparse_fraction=0.0)
    assert looks_like_real_data(recs, declared_provenance=SYNTHETIC_PROVENANCE) is False


def test_default_domain_is_neonatal_and_matches_the_bundled_corpus() -> None:
    assert DEFAULT_DOMAIN == "neonatal"
    assert set(DOMAIN_LIBS) == {"neonatal", "adult_inpatient"}


def test_neonatal_profile_produces_neonatal_content() -> None:
    recs = generate(40, seed=11, sparse_fraction=0.0, domain="neonatal")
    problems = {p for r in recs for p in r.problems}
    assert problems & {"prematurity", "neonatal jaundice", "possible serious bacterial infection"}
    assert not (problems & {"COPD", "atrial fibrillation"})
    # weight-based dosing and neonatal encounter fields are populated
    assert any("mg/kg" in (m.dose or "") or "IU/kg" in (m.dose or "")
               for r in recs for m in r.medications)
    assert any(r.encounter.birth_weight_g is not None for r in recs)
    assert any(v.weight_g is not None for r in recs for v in r.vitals)


def test_adult_profile_still_available() -> None:
    recs = generate(20, seed=5, sparse_fraction=0.0, domain="adult_inpatient")
    problems = {p for r in recs for p in r.problems}
    assert problems & {"COPD", "type 2 diabetes mellitus", "atrial fibrillation"}
    assert not (problems & {"prematurity", "neonatal jaundice"})


def test_unknown_domain_rejected() -> None:
    with pytest.raises(ValueError):
        generate(3, seed=1, sparse_fraction=0.0, domain="paediatric_icu")
