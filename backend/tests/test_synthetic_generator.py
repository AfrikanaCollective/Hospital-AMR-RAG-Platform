"""Synthetic record generator produces valid, clearly-synthetic data (PRD-006, PRD-081)."""

from __future__ import annotations

from app.schemas.record import SYNTHETIC_PROVENANCE
from scripts.generate_synthetic_records import generate


def test_generates_requested_count_and_is_deterministic() -> None:
    a = generate(20, seed=1, sparse_fraction=0.25)
    b = generate(20, seed=1, sparse_fraction=0.25)
    assert len(a) == 20
    assert [r.record_id for r in a] == [r.record_id for r in b]


def test_every_record_marked_synthetic() -> None:
    recs = generate(30, seed=7, sparse_fraction=0.3)
    assert all(r.dataset_provenance == SYNTHETIC_PROVENANCE for r in recs)
    assert all(r.mrn.startswith("SYN-") for r in recs)


def test_some_records_are_sparse_for_hard_case_generation() -> None:
    recs = generate(40, seed=3, sparse_fraction=0.5)
    sparse_like = [r for r in recs if not r.labs and not r.vitals]
    assert sparse_like, "expected some sparse records (PRD-064)"


def test_real_data_heuristic_trusts_the_synthetic_marker() -> None:
    from app.ingestion.records import looks_like_real_data

    recs = generate(5, seed=1, sparse_fraction=0.0)
    assert looks_like_real_data(recs, declared_provenance=SYNTHETIC_PROVENANCE) is False
