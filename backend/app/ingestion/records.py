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

**Dedupe on MRN (DEVIATIONS.md #57).** `patient.mrn_enc` alone cannot support
a dedupe lookup — AEAD ciphertext is randomly-nonced, so two encryptions of
the same MRN never compare equal. `patient.mrn_hash`
(`CryptoProvider.deterministic_hash`, an HMAC keyed off the KEK) is a stable
lookup key computed from the plaintext MRN but never itself decrypted or
exposed. `_find_patient_by_mrn_hash` is the only DB read in this module —
indirection so tests exercise the real dedup/encryption/field-index logic
with a trivial fake session, without needing a real Postgres.

**Wide file upload — `parse_wide_upload` (DEVIATIONS.md #64).** JSON supports
the full `PatientRecord` schema losslessly (a bare list, or the same
`{schema_version, dataset_provenance, records: [...]}` envelope
`scripts/generate_synthetic_records.py` writes). CSV supports scalar +
one-level-nested (`encounter.*`) fields only, via dotted column headers — a
flat CSV row cannot represent a list (`medications`, `labs`, `vitals`,
`examination_findings`, `interventions`, `problems`, `allergies`); a CSV
column referring to one of those is rejected rather than silently dropped or
misparsed.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.crypto.provider import CryptoProvider, get_crypto
from app.db.models.records import Patient
from app.db.models.records import PatientRecord as PatientRecordRow
from app.schemas.enums import DataClass
from app.schemas.record import (
    DEIDENTIFIED_PROVENANCE,
    SYNTHETIC_PROVENANCE,
    PatientRecord,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_CSV_LIST_FIELD_PREFIXES = (
    "medications",
    "labs",
    "vitals",
    "examination_findings",
    "interventions",
    "maternal_risk_factors",
    "problems",
    "allergies",
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

# Identity/meta fields excluded from field_index: always required by the
# schema, so a presence flag for them carries no information.
_FIELD_INDEX_EXCLUDED = frozenset({"schema_version", "dataset_provenance", "record_id", "mrn"})


class RealDataSuspectedError(RuntimeError):
    """Raised when an ingest batch fails the real-data guard (PRD-081)."""


class MissingAttestationError(RuntimeError):
    """Raised when a de-identified batch is submitted without a complete
    attestation (DEVIATIONS #33)."""


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
            missing = (
                attestation.missing_fields() if attestation else list(REQUIRED_ATTESTATION_FIELDS)
            )
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


# Repeating groups shaped {name_key: <concept>, value_key: <the actual clinical
# value>} (ExamFinding.present, Intervention/Medication.active, LabResult.value)
# rather than "wide" per-concept fields (Vitals). For these, `name_key`'s value
# (e.g. "apnoea") is itself a field NAME for indexing purposes — like
# `vitals.heart_rate_bpm`'s field name is a literal model attribute — never a
# clinical value; only `value_key`'s null-ness is ever indexed, never its
# content. Fixes a bug where `criteria.field_present_in_index`'s documented
# indexed-key convention (`vitals.0.heart_rate_bpm`) was never actually
# produced for repeating groups, so `missing_info_agent` (SCOPE-2.2) reported
# every criterion field sourced from a list as missing even when recorded.
_NAME_VALUE_LIST_FIELDS: dict[str, tuple[str, str]] = {
    "examination_findings": ("name", "present"),
    "maternal_risk_factors": ("name", "present"),
    "interventions": ("name", "active"),
    "medications": ("name", "active"),
    "labs": ("analyte", "value"),
}


def _flatten_presence(value: Any, prefix: str, out: dict[str, bool]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten_presence(v, f"{prefix}.{k}" if prefix else k, out)
    elif isinstance(value, list):
        out[prefix] = len(value) > 0
        name_value_keys = _NAME_VALUE_LIST_FIELDS.get(prefix)
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                continue  # scalar-list field (problems, allergies) -> flat flag only
            if name_value_keys is not None:
                name_key, value_key = name_value_keys
                name = item.get(name_key)
                if name:
                    out[f"{prefix}.{idx}.{name}"] = item.get(value_key) is not None
            else:
                _flatten_presence(item, f"{prefix}.{idx}", out)
    else:
        out[prefix] = value is not None


def compute_field_index(record: PatientRecord) -> dict[str, bool]:
    """Field NAMES + null-ness ONLY (PRD-080/ARCH §4.2) — never a value, so the
    missing-info agent (SCOPE-2.2) can work without decrypting `payload_enc`.
    Repeating groups (`vitals`, `labs`, `examination_findings`, `interventions`,
    `medications`) get both a flat `{field}` any-recorded flag and per-item
    indexed keys (`vitals.0.heart_rate_bpm`, `examination_findings.0.apnoea`)
    so `app.records.criteria.field_present_in_index` can resolve a specific
    concept without decrypting."""
    out: dict[str, bool] = {}
    for k, v in record.model_dump(mode="json").items():
        if k in _FIELD_INDEX_EXCLUDED:
            continue
        _flatten_presence(v, k, out)
    return out


def _find_patient_by_mrn_hash(session: Session, mrn_hash: str) -> Patient | None:
    return session.execute(select(Patient).where(Patient.mrn_hash == mrn_hash)).scalar_one_or_none()


def _get_or_create_patient(
    session: Session, mrn: str, *, data_class: DataClass, source: str, crypto: CryptoProvider
) -> Patient:
    mrn_hash = crypto.deterministic_hash(mrn.encode("utf-8"))
    existing = _find_patient_by_mrn_hash(session, mrn_hash)
    if existing is not None:
        return existing
    patient = Patient(
        mrn_enc=crypto.encrypt(mrn.encode("utf-8"), aad=mrn_hash.encode("utf-8")),
        mrn_hash=mrn_hash,
        source=source,
        data_class=data_class.value,
    )
    session.add(patient)
    session.flush()
    return patient


def ingest_records(
    session: Session,
    records: list[PatientRecord],
    *,
    declared_provenance: str | None,
    dataset_id: str | None = None,
    attestation: DatasetAttestation | None = None,
    source: str = "file",
) -> list[uuid.UUID]:
    """Validate the batch (`guard_batch`), then append one `patient_record`
    snapshot per record, deduping `patient` rows on MRN. Returns the new
    `patient_record` ids, in input order."""
    data_class = guard_batch(
        records, declared_provenance=declared_provenance, attestation=attestation
    )
    crypto = get_crypto()
    batch_id = uuid.uuid4()
    patient_record_ids: list[uuid.UUID] = []
    for record in records:
        patient = _get_or_create_patient(
            session, record.mrn, data_class=data_class, source=source, crypto=crypto
        )
        payload_enc = crypto.encrypt(
            record.model_dump_json().encode("utf-8"), aad=str(patient.id).encode("utf-8")
        )
        row = PatientRecordRow(
            patient_id=patient.id,
            schema_version=record.schema_version,
            ingested_at=datetime.now(UTC),
            payload_enc=payload_enc,
            field_index=compute_field_index(record),
            dataset_id=dataset_id,
            source_batch_id=batch_id,
        )
        session.add(row)
        session.flush()
        patient_record_ids.append(row.id)
    return patient_record_ids


def _unflatten_wide_csv_row(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw_value in row.items():
        if any(
            key == prefix or key.startswith(f"{prefix}.") for prefix in _CSV_LIST_FIELD_PREFIXES
        ):
            raise ValueError(
                f"CSV column {key!r} refers to a list field; upload JSON instead for records "
                "with medications/labs/vitals/examination_findings/interventions/problems/"
                "allergies (DEVIATIONS.md #64)"
            )
        value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if value in ("", None):
            continue  # an empty cell means the field is absent, not an empty string
        if "." in key:
            parts = key.split(".")
            cur = out
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            cur[parts[-1]] = value
        else:
            out[key] = value
    return out


def parse_wide_upload(content: bytes, filename: str) -> list[PatientRecord]:
    """Parse a wide file upload (`POST /ingest/records/file`; ARCH §5.2) —
    `.json` (full schema) or `.csv` (scalar + one-level-nested fields only,
    DEVIATIONS.md #64). Raises `ValueError`/`pydantic.ValidationError` on a
    malformed upload; the route maps those to an HTTP 422."""
    name = filename.lower()
    if name.endswith(".json"):
        data = json.loads(content)
        rows = data["records"] if isinstance(data, dict) and "records" in data else data
        if not isinstance(rows, list):
            raise ValueError("JSON upload must be a list of records, or {'records': [...]}")
        return [PatientRecord(**row) for row in rows]
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return [PatientRecord(**_unflatten_wide_csv_row(row)) for row in reader]
    raise ValueError(f"unsupported file type (expected .json or .csv): {filename!r}")
