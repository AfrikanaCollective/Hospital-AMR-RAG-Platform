"""Patient-record schema (PRD-002, PRD-003, PRD-080, PRD-A3).

This is the fixed structured schema. Synthetic data mirrors it exactly
(see data/record_schema.json and scripts/generate_synthetic_records.py).
Every field is PHI by default (PRD-080). `dataset_provenance` marks
project-generated synthetic batches so the ingestion real-data heuristic
accepts them (DEVIATIONS.md #21).

Phase 1: a representative schema sufficient to scaffold ingestion, field_index,
and the missing-info agent. Fields may be refined in Phase 2 (log any change in
DEVIATIONS.md).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0.0"
SYNTHETIC_PROVENANCE = "synthetic-generator-v1"


class Vitals(BaseModel):
    recorded_at: datetime | None = None
    heart_rate_bpm: float | None = None
    resp_rate_bpm: float | None = None
    systolic_bp_mmhg: float | None = None
    diastolic_bp_mmhg: float | None = None
    temperature_c: float | None = None
    spo2_percent: float | None = None


class LabResult(BaseModel):
    analyte: str
    value: float | None = None
    unit: str | None = None
    collected_at: datetime | None = None
    reference_low: float | None = None
    reference_high: float | None = None


class Medication(BaseModel):
    name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    started_at: datetime | None = None
    active: bool = True


class Encounter(BaseModel):
    admitted_at: datetime | None = None
    ward: str | None = None
    care_setting: str | None = None  # e.g. ED, general ward, HDU, ICU
    presenting_complaint: str | None = None
    triage_category: str | None = None


class PatientRecord(BaseModel):
    """One structured record snapshot. All fields PHI by default."""

    schema_version: str = SCHEMA_VERSION
    dataset_provenance: str | None = Field(
        default=None,
        description="Set to the synthetic-generator marker for project-generated "
        "batches; unmarked 'real-looking' batches are rejected on ingest.",
    )

    # identity (synthetic)
    record_id: str
    mrn: str
    given_name: str
    family_name: str
    date_of_birth: date | None = None
    sex: str | None = None

    # clinical context
    encounter: Encounter = Field(default_factory=Encounter)
    problems: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    vitals: list[Vitals] = Field(default_factory=list)
    labs: list[LabResult] = Field(default_factory=list)

    # free text (encrypted at rest; treated as PHI)
    clinical_notes: str | None = None

    # consent / opt-out flags honoured by the access layer (ARCH §21b)
    consent_flags: dict[str, bool] = Field(default_factory=dict)


class RecordIngestBatch(BaseModel):
    schema_version: str = SCHEMA_VERSION
    dataset_provenance: str
    records: list[PatientRecord]
