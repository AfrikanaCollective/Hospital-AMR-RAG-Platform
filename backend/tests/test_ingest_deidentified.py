"""De-identified ingestion: attestation gate + data-class guard (ARCH-039; DEVIATIONS #33)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.records import (
    REQUIRED_ATTESTATION_FIELDS,
    DatasetAttestation,
    MissingAttestationError,
    RealDataSuspectedError,
    guard_batch,
)
from app.schemas.enums import DataClass
from app.schemas.record import (
    DEIDENTIFIED_PROVENANCE,
    SYNTHETIC_PROVENANCE,
    PatientRecord,
)
from scripts.ingest_deidentified_records import main as ingest_main
from scripts.ingest_deidentified_records import parse_front_matter

REPO = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO / "data/patient_records/deidentified/newborn_nbu_2021"


def _rec() -> PatientRecord:
    return PatientRecord(record_id="1", mrn="DEID-1")


COMPLETE = {f: f"filled-{f}" for f in REQUIRED_ATTESTATION_FIELDS}


def test_synthetic_batch_passes_without_attestation() -> None:
    assert guard_batch([_rec()], declared_provenance=SYNTHETIC_PROVENANCE) is DataClass.SYNTHETIC


def test_deidentified_without_attestation_is_refused() -> None:
    with pytest.raises(MissingAttestationError):
        guard_batch([_rec()], declared_provenance=DEIDENTIFIED_PROVENANCE)


def test_deidentified_with_incomplete_attestation_is_refused() -> None:
    incomplete = {**COMPLETE, "consent_basis": "TODO_CONFIRM"}
    with pytest.raises(MissingAttestationError):
        guard_batch(
            [_rec()],
            declared_provenance=DEIDENTIFIED_PROVENANCE,
            attestation=DatasetAttestation(incomplete),
        )


def test_deidentified_with_complete_attestation_is_accepted() -> None:
    dc = guard_batch(
        [_rec()],
        declared_provenance=DEIDENTIFIED_PROVENANCE,
        attestation=DatasetAttestation(COMPLETE),
    )
    assert dc is DataClass.DEIDENTIFIED


def test_unmarked_real_looking_batch_is_hard_rejected() -> None:
    with pytest.raises(RealDataSuspectedError):
        guard_batch([_rec()], declared_provenance=None)


def test_shipped_dataset_md_front_matter_has_all_attestation_fields() -> None:
    fm = parse_front_matter(DATASET_DIR / "DATASET.md")
    for f in REQUIRED_ATTESTATION_FIELDS:
        assert f in fm  # every attestation field is present as a key


def test_ingest_script_refuses_without_attest_flag() -> None:
    rc = ingest_main(["--dataset-dir", str(DATASET_DIR)])
    assert rc == 2


def test_ingest_script_refuses_incomplete_attestation(tmp_path: Path) -> None:
    d = tmp_path / "ds"
    d.mkdir()
    (d / "rag_dataset.csv").write_text(
        '"key","field_name","field_value","context"\n1,"age_days","1","demographics"\n'
    )
    (d / "field_mapping.yaml").write_text(
        'dataset_id: t\nprovenance: deidentified-anonymised\nschema_version: "1.3.0"\n'
        'identity: { record_id: "{key}", mrn: "DEID-{key}" }\nfields: {}\nlist_targets: {}\n'
    )
    fm = "\n".join(
        f"{f}: {'TODO_CONFIRM' if f == 'licence' else 'x'}" for f in REQUIRED_ATTESTATION_FIELDS
    )
    (d / "DATASET.md").write_text(f"---\n{fm}\n---\n# incomplete\n")
    rc = ingest_main(["--dataset-dir", str(d), "--attest-deidentified"])
    assert rc == 2


@pytest.mark.skipif(
    not (DATASET_DIR / "rag_dataset.csv").exists(),
    reason="real de-identified dataset not present (expected in CI)",
)
def test_ingest_script_runs_with_complete_attestation(tmp_path: Path) -> None:
    out = tmp_path / "records.json"
    rc = ingest_main(
        [
            "--dataset-dir",
            str(DATASET_DIR),
            "--attest-deidentified",
            "--limit",
            "25",
            "--out",
            str(out),
        ]
    )
    assert rc == 0 and out.exists()
    import json

    payload = json.loads(out.read_text())
    assert payload["data_class"] == "deidentified"
    assert payload["count"] == 25
    assert payload["schema_version"] == "1.4.0"
