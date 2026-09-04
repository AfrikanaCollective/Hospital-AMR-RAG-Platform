"""Patient-record schema (PRD-002, PRD-003, PRD-080, PRD-A3).

This is the fixed structured schema. Every field is PHI by default (PRD-080).

Two legitimate data classes carry a `dataset_provenance` marker so the
ingestion real-data guard accepts them (see `app.ingestion.records`):
  - `synthetic-generator-v1`  — project-generated synthetic data (DEVIATIONS #21)
  - `deidentified-anonymised` — an operator-supplied, attested de-identified
    dataset (DEVIATIONS #33; requires an attestation, then treated exactly as
    PHI end to end)
Unmarked "real-looking" batches are still rejected.

Design principles (keep this schema small and source-agnostic — DEVIATIONS #39):
  - It is a **flat, point-in-time-or-interval clinical snapshot**, not a full
    EHR. One canonical model; every source (synthetic generator, EAV file,
    future REST API) maps *onto* it via its own adapter / mapping spec — no
    source-specific field ever lands here.
  - **Temporal entities** (`Medication`, `Intervention`) carry an optional
    `started_at` / `stopped_at` pair (an interval, either end may be null).
    **Point-in-time entities** (`Vitals`, `LabResult`, `ExamFinding`) carry a
    single `*_at`. Do not add bespoke per-entity time fields.
  - Repeated data is `list[TypedSubModel]` (validates + round-trips through
    JSON APIs), never a free-form `dict` bag.
  - Evolution is **additive only** and gated by `schema_version`; an API
    client sending an older version still validates.

Version history:
  1.0.0  initial (adult inpatient fields) — DEVIATIONS #23
  1.1.0  + Vitals.weight_g/mean_bp_mmhg, Encounter.gestational_age_weeks/
         birth_weight_g/day_of_life (neonatal RECORD_DOMAIN) — DEVIATIONS #32
  1.2.0  + Vitals.capillary_refill_seconds, ExamFinding + examination_findings[],
         Intervention + interventions[]; given_name/family_name widened to
         optional (de-identified data has no names, C2) — DEVIATIONS #35, #38
  1.3.0  + Medication.stopped_at, Intervention.stopped_at (interval end) — DEVIATIONS #39
All additions are optional/nullable; older records still validate.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.3.0"
SYNTHETIC_PROVENANCE = "synthetic-generator-v1"
DEIDENTIFIED_PROVENANCE = "deidentified-anonymised"


class Vitals(BaseModel):
    recorded_at: datetime | None = None
    heart_rate_bpm: float | None = None
    resp_rate_bpm: float | None = None
    systolic_bp_mmhg: float | None = None
    diastolic_bp_mmhg: float | None = None
    mean_bp_mmhg: float | None = None  # neonatal monitoring often records mean BP only
    temperature_c: float | None = None
    spo2_percent: float | None = None
    weight_g: float | None = None  # weight is a monitored vital in neonatal care
    capillary_refill_seconds: float | None = None  # perfusion (1.2.0)


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
    stopped_at: datetime | None = None  # interval end; null = ongoing / unknown (1.3.0)
    active: bool = True


class ExamFinding(BaseModel):
    """A history/examination sign, structured so present/absent is preserved (1.2.0)."""

    name: str
    present: bool
    recorded_at: datetime | None = None


class Intervention(BaseModel):
    """A supportive/therapeutic intervention (respiratory support, fluids, feeds,
    KMC, oxygen, anticonvulsant, etc.) — distinct from `medications` (1.2.0)."""

    name: str
    active: bool = True
    started_at: datetime | None = None
    stopped_at: datetime | None = None  # interval end; null = ongoing / unknown (1.3.0)


class Encounter(BaseModel):
    admitted_at: datetime | None = None
    ward: str | None = None
    care_setting: str | None = None  # adult: ED/ward/HDU/ICU; neonatal: NBU/KMC/nursery/postnatal
    presenting_complaint: str | None = None
    triage_category: str | None = None
    # neonatal context (nullable; DEVIATIONS.md #32)
    gestational_age_weeks: float | None = None
    birth_weight_g: float | None = None
    day_of_life: int | None = None


class PatientRecord(BaseModel):
    """One structured record snapshot. All fields PHI by default."""

    schema_version: str = SCHEMA_VERSION
    dataset_provenance: str | None = Field(
        default=None,
        description="synthetic-generator-v1 | deidentified-anonymised; unmarked "
        "'real-looking' batches are rejected on ingest.",
    )

    # identity
    record_id: str
    mrn: str
    # C2 (DEVIATIONS #35, confirmed #38): de-identified datasets have no names.
    given_name: str | None = None
    family_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None

    # clinical context
    encounter: Encounter = Field(default_factory=Encounter)
    problems: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    examination_findings: list[ExamFinding] = Field(default_factory=list)  # 1.2.0
    interventions: list[Intervention] = Field(default_factory=list)  # 1.2.0
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
