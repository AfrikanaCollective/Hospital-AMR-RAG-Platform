"""Patient-record ingestion — file (CSV/JSON + EAV) + API (ARCH §5.2; PRD-002, PRD-003).

- validate against app.schemas.record.PatientRecord (schema_version),
- dedupe patients on MRN, append a patient_record snapshot,
- envelope-encrypt payload_enc (ARCH-032),
- compute field_index (field NAMES + null-ness ONLY — no values),
- record the data class on `patient.data_class` / `patient_record.dataset_id`.

Data-class guard (DEVIATIONS #16, #21, #33):
  - `synthetic`     — trusted via the `synthetic-generator-v1` provenance marker.
  - `deidentified`  — trusted ONLY with a complete operator **attestation**
    (`DATASET.md` front-matter + explicit intent); then treated exactly as PHI
    everywhere downstream.
  - anything else    — a real-looking batch with no marker and no attestation is
    hard-rejected (heuristic detail is Phase 2).

No embedding of record content by default (ARCH-023).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.enums import DataClass
from app.schemas.record import (
    DEIDENTIFIED_PROVENANCE,
    SYNTHETIC_PROVENANCE,
    PatientRecord,
)

REQUIRED_ATTESTATION_FIELDS = (
    "source",
    "collection_period",
    "site",
    "deidentification_method",
    "deidentification_standard",
    "consent_basis",
    "licence",
    "attested_by",
    "attested_date",
)


class RealDataSuspectedError(RuntimeError):
    """Raised when an ingest batch fails the real-data guard (PRD-081)."""


class MissingAttestationError(RuntimeError):
    """Raised when a de-identified batch is submitted without a complete attestation (DEVIATIONS #33)."""


@dataclass(frozen=True)
class DatasetAttestation:
    """Operator attestation for a `deidentified` dataset (from DATASET.md front-matter)."""

    values: dict[str, str]

    def missing_fields(self) -> list[str]:
        return [
            f
            for f in REQUIRED_ATTESTATION_FIELDS
            if not str(self.values.get(f, "")).strip()
            or str(self.values.get(f, "")).strip().upper().startswith("TODO")
        ]

    def is_complete(self) -> bool:
        return not self.missing_fields()


def resolve_data_class(provenance: str | None) -> DataClass | None:
    return {
        SYNTHETIC_PROVENANCE: DataClass.SYNTHETIC,
        DEIDENTIFIED_PROVENANCE: DataClass.DEIDENTIFIED,
    }.get(provenance or "")


def guard_batch(
    records: list[PatientRecord],
    *,
    declared_provenance: str | None,
    attestation: DatasetAttestation | None = None,
) -> DataClass:
    """Return the accepted DataClass, or raise. `looks_like_real_data` wraps this."""
    dc = resolve_data_class(declared_provenance)
    if dc is DataClass.SYNTHETIC:
        return dc
    if dc is DataClass.DEIDENTIFIED:
        if attestation is None or not attestation.is_complete():
            missing = attestation.missing_fields() if attestation else list(REQUIRED_ATTESTATION_FIELDS)
            raise MissingAttestationError(
                "de-identified dataset requires a complete operator attestation "
                f"(DATASET.md); missing/blank: {missing} (DEVIATIONS #33)"
            )
        return dc
    raise RealDataSuspectedError(
        "batch is neither marked synthetic nor an attested de-identified dataset; "
        "refusing ingestion (PRD-081 / DEVIATIONS #16)"
    )


def looks_like_real_data(
    records: list[PatientRecord],
    *,
    declared_provenance: str | None,
    attestation: DatasetAttestation | None = None,
) -> bool:
    """Back-compat: True if the batch should be rejected. Synthetic and
    attested-de-identified batches return False; everything else raises via
    `guard_batch` (Phase 2 will add the plausibility heuristic for the
    unmarked case instead of raising outright)."""
    try:
        guard_batch(records, declared_provenance=declared_provenance, attestation=attestation)
        return False
    except (RealDataSuspectedError, MissingAttestationError):
        raise


def ingest_records(
    records: list[PatientRecord],
    *,
    declared_provenance: str | None,
    dataset_id: str | None = None,
    attestation: DatasetAttestation | None = None,
) -> None:
    data_class = guard_batch(
        records, declared_provenance=declared_provenance, attestation=attestation
    )
    _ = data_class  # persisted on patient.data_class in Phase 2
    raise NotImplementedError("Phase 2 (ARCH §5.2): persist snapshots + field_index + audit")
