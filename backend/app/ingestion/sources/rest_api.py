"""RestApiPullSource — STUB for a future pull-API integration (ARCH-039; PRD-003).

Seam for pulling patient-level data from an upstream clinical API that returns
the same variables as the newborn EAV dataset. It reuses the same
`field_mapping.yaml` contract (via `app.ingestion.eav.MappingSpec`), so the
mapping is defined once.

Phase 2+ implements:
  - configurable base URL + auth (`PATIENT_API_URL`, service credential),
  - EAV-or-wide response handling,
  - incremental backfill (by `key`, or `updated-since` cursor),
  - the same attestation gate as the file path when the upstream is a
    de-identified extract.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.ingestion.eav import MappingSpec
from app.ingestion.sources.base import SourceDescription
from app.schemas.record import PatientRecord


class RestApiPullSource:
    def __init__(self, base_url: str, mapping_path: str, *, dataset_id: str) -> None:
        self.base_url = base_url
        self.spec = MappingSpec.from_yaml(mapping_path)
        self.dataset_id = dataset_id

    def describe(self) -> SourceDescription:  # pragma: no cover - stub
        raise NotImplementedError("Phase 2+: RestApiPullSource (ARCH-039)")

    def iter_records(
        self, *, limit: int | None = None
    ) -> Iterator[PatientRecord]:  # pragma: no cover
        raise NotImplementedError(
            "Phase 2+: pull from PATIENT_API_URL, pivot if EAV, apply the shared "
            "mapping spec, enforce the attestation gate, support incremental backfill."
        )
