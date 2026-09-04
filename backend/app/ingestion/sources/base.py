"""PatientDataSource interface (ARCH-039)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from app.schemas.enums import DataClass
from app.schemas.record import PatientRecord


@dataclass(frozen=True)
class SourceDescription:
    dataset_id: str
    data_class: DataClass
    provenance: str
    origin: str  # file path, API base URL, ...


class PatientDataSource(Protocol):
    def describe(self) -> SourceDescription: ...
    def iter_records(self, *, limit: int | None = None) -> Iterator[PatientRecord]: ...
