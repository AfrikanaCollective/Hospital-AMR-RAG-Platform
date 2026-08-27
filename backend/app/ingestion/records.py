"""Patient-record ingestion — file (CSV/JSON) + API (ARCH §5.2; PRD-002, PRD-003).

- validate against app.schemas.record.PatientRecord (schema_version),
- dedupe patients on synthetic MRN, append a patient_record snapshot,
- envelope-encrypt payload_enc (ARCH-032),
- compute field_index (field NAMES + null-ness ONLY — no values),
- run the real-data heuristic: reject a batch that looks like real data unless
  it carries the synthetic-generator provenance marker
  (SYNTHETIC_PROVENANCE) (DEVIATIONS.md #16, #21).

No embedding of record content by default (ARCH-023).
Phase 2 implements the pipeline; the heuristic is defense-in-depth, not a
guarantee.
"""

from __future__ import annotations

from app.schemas.record import SYNTHETIC_PROVENANCE, PatientRecord


class RealDataSuspectedError(RuntimeError):
    """Raised when an ingest batch fails the real-data heuristic (PRD-081)."""


def looks_like_real_data(records: list[PatientRecord], *, declared_provenance: str | None) -> bool:
    """True if the batch should be rejected. Phase 2 fills in the heuristics
    (name/identifier entropy, DOB plausibility, free-text PII signals).
    A batch explicitly marked with the synthetic-generator provenance is
    trusted (returns False)."""
    if declared_provenance == SYNTHETIC_PROVENANCE:
        return False
    raise NotImplementedError("Phase 2: real-data heuristic (DEVIATIONS.md #21)")


def ingest_records(records: list[PatientRecord], *, declared_provenance: str | None) -> None:
    raise NotImplementedError("Phase 2 (ARCH §5.2)")
