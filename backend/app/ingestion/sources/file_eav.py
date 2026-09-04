"""FileEavSource — EAV/long CSV + mapping spec (ARCH-039; DEVIATIONS #34)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from app.ingestion.eav import MappingSpec, build_records
from app.ingestion.sources.base import SourceDescription
from app.schemas.enums import DataClass
from app.schemas.record import DEIDENTIFIED_PROVENANCE, SYNTHETIC_PROVENANCE, PatientRecord


class FileEavSource:
    def __init__(self, csv_path: str | Path, mapping_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self.spec = MappingSpec.from_yaml(mapping_path)

    def describe(self) -> SourceDescription:
        data_class = {
            SYNTHETIC_PROVENANCE: DataClass.SYNTHETIC,
            DEIDENTIFIED_PROVENANCE: DataClass.DEIDENTIFIED,
        }.get(self.spec.provenance, DataClass.DEIDENTIFIED)
        return SourceDescription(
            dataset_id=self.spec.dataset_id,
            data_class=data_class,
            provenance=self.spec.provenance,
            origin=str(self.csv_path),
        )

    def iter_records(self, *, limit: int | None = None) -> Iterator[PatientRecord]:
        yield from build_records(self.csv_path, self.spec, limit=limit)
