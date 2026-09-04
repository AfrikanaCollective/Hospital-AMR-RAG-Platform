"""Patient-data sources (ARCH-039; DEVIATIONS #34).

A `PatientDataSource` yields validated `PatientRecord` objects from some
upstream. `FileEavSource` reads an EAV/long CSV + a mapping spec (implemented).
`RestApiPullSource` is the seam for a future pull-API integration that returns
the same variables and reuses the same `field_mapping.yaml` (stub — Phase 2+).
"""

from app.ingestion.sources.base import PatientDataSource, SourceDescription
from app.ingestion.sources.file_eav import FileEavSource

__all__ = ["PatientDataSource", "SourceDescription", "FileEavSource"]
