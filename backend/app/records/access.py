"""Patient-record read access (ARCH §4.2, §10.2, ARCH-034; PRD-080, PRD-084).

The ONLY module that decrypts `patient_record.payload_enc`. Backs the two
tools `patient_record_agent` / `missing_info_agent` are allowed to call:
`list_record_fields` (names only, from `field_index` — no decryption needed)
and `get_patient_fields` (decrypts, projects only the requested field paths
the caller's role is authorized for that purpose, audits the exact list
requested plus what was denied/masked).

**Field-level policy (DEVIATIONS.md #70, #87):** `get_patient_fields` gates
every requested field that actually exists in the record through
`app.auth.rbac.resolve_field_effects` — the DB-backed `records.record_field_policy`
`(role, purpose, field_path) -> allow|deny|mask` table — in one bulk query.
`deny` drops the field from the result entirely (as if absent); `mask`
substitutes `_MASKED_PLACEHOLDER` for the real value, so a caller can tell
"restricted" apart from "not on file"; `allow` returns the real value. No
matching policy row (neither an exact field-path row nor a `(role, purpose,
"*")` wildcard row) fails **closed** to `deny`. Two things sit beneath the
policy table as a hard floor, not overridable by any policy row: (a)
`get_patient_fields` never returns direct identifiers (`given_name`/
`family_name`/`mrn`) regardless of what is requested or what a policy row
says — the one thing every in-scope purpose (guideline matching, stage
classification, missing-info) never needs; (b) it returns only the field
paths the caller explicitly asked for, nothing else. Every read is audited
with the exact field list requested, patient_id, purpose, and (when
non-empty) the denied/masked subsets.

Feature paths are "latest-projected": a repeating group (`vitals`, `labs`)
collapses to its most recent entry to make comparison against a matched
guideline's stage/missing-info criteria tractable — see
`app.records.criteria` for how a criterion's free-text field name maps onto
these paths.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.audit.log import write_event
from app.auth.rbac import resolve_field_effects
from app.crypto.provider import get_crypto
from app.db.models.records import PatientRecord as PatientRecordRow
from app.schemas.record import PatientRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_RESOLVE_FIELD_EFFECTS_FN = resolve_field_effects

# Never returned by get_patient_fields regardless of what is requested
# (DEVIATIONS.md #70) — direct identifiers no in-scope purpose needs.
_NEVER_RETURNED_FIELDS = frozenset({"given_name", "family_name", "mrn", "record_id"})

# Substituted for the real value when record_field_policy resolves `mask`
# (DEVIATIONS.md #87) — distinguishes "restricted by policy" from "not on file".
_MASKED_PLACEHOLDER = "[masked by policy]"

# Repeating groups that collapse to their most recent entry when projected
# into flat "latest" feature paths.
_TIME_SERIES_FIELDS = ("vitals", "labs")


class PatientNotFoundError(LookupError):
    """Raised when a patient has no ingested record."""


def _find_latest_patient_record(session: Session, patient_id: uuid.UUID) -> PatientRecordRow | None:
    return session.execute(
        select(PatientRecordRow)
        .where(PatientRecordRow.patient_id == patient_id)
        .order_by(PatientRecordRow.ingested_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def decrypt_record(row: PatientRecordRow) -> PatientRecord:
    crypto = get_crypto()
    plaintext = crypto.decrypt(row.payload_enc, aad=str(row.patient_id).encode("utf-8"))
    return PatientRecord.model_validate_json(plaintext)


def _latest_by_time(items: list[dict], time_key: str) -> dict | None:
    timed = [i for i in items if i.get(time_key)]
    if timed:
        return max(timed, key=lambda i: i[time_key])
    return items[-1] if items else None


def _encounter_features(dumped: dict) -> dict[str, Any]:
    return {f"encounter.{k}": v for k, v in dumped.get("encounter", {}).items() if v is not None}


def _latest_vitals_features(dumped: dict) -> dict[str, Any]:
    latest = _latest_by_time(dumped.get("vitals", []), "recorded_at")
    if not latest:
        return {}
    return {f"vitals.{k}": v for k, v in latest.items() if k != "recorded_at" and v is not None}


def _latest_labs_features(dumped: dict) -> dict[str, Any]:
    by_analyte: dict[str, dict] = {}
    for lab in dumped.get("labs", []):
        analyte = lab.get("analyte")
        if not analyte:
            continue
        existing = by_analyte.get(analyte)
        newer = existing is None or (
            (lab.get("collected_at") or "") > (existing.get("collected_at") or "")
        )
        if newer:
            by_analyte[analyte] = lab
    return {
        f"labs.{analyte}": lab["value"]
        for analyte, lab in by_analyte.items()
        if lab.get("value") is not None
    }


def _list_and_flag_features(dumped: dict) -> dict[str, Any]:
    features: dict[str, Any] = {}
    if dumped.get("problems"):
        features["problems"] = dumped["problems"]
    if dumped.get("allergies"):
        features["allergies"] = dumped["allergies"]
    active_meds = [m["name"] for m in dumped.get("medications", []) if m.get("active")]
    if active_meds:
        features["medications.active"] = active_meds
    active_interventions = [i["name"] for i in dumped.get("interventions", []) if i.get("active")]
    if active_interventions:
        features["interventions.active"] = active_interventions
    for finding in dumped.get("examination_findings", []):
        name = finding.get("name")
        if name:
            features[f"examination_findings.{name}"] = finding.get("present")
    if dumped.get("date_of_birth"):
        features["date_of_birth"] = dumped["date_of_birth"]
    if dumped.get("sex"):
        features["sex"] = dumped["sex"]
    return features


def extract_features(record: PatientRecord) -> dict[str, Any]:
    """Flatten a `PatientRecord` into clinically-useful "latest" feature
    paths (ARCH §10.2 patient-record agent). Repeating groups collapse to
    their most recent entry; identity fields are excluded (never needed for
    guideline matching / stage classification / missing-info)."""
    dumped = record.model_dump(mode="json")
    return {
        **_encounter_features(dumped),
        **_latest_vitals_features(dumped),
        **_latest_labs_features(dumped),
        **_list_and_flag_features(dumped),
    }


def list_record_fields(session: Session, patient_id: uuid.UUID) -> list[str]:
    """Field NAMES only (from `field_index`) — no decryption (PRD-080/ARCH §4.2)."""
    row = _find_latest_patient_record(session, patient_id)
    if row is None:
        raise PatientNotFoundError(f"no ingested record for patient_id={patient_id}")
    return sorted(k for k, present in row.field_index.items() if present)


def get_record_field_index(session: Session, patient_id: uuid.UUID) -> dict[str, bool]:
    """Raw field_index (names + null-ness) — lets missing-info check presence
    for a `list`-shaped concept without decrypting (see `app.records.criteria`)."""
    row = _find_latest_patient_record(session, patient_id)
    if row is None:
        raise PatientNotFoundError(f"no ingested record for patient_id={patient_id}")
    return dict(row.field_index)


def get_patient_fields(
    session: Session,
    patient_id: uuid.UUID,
    field_paths: list[str],
    *,
    purpose: str,
    actor_role: str,
    actor_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Return ONLY the requested, policy-authorized field values (ARCH §10.2,
    ARCH-034). `actor_role` gates every present field through
    `record_field_policy(actor_role, purpose, field_path)`: `deny` drops it,
    `mask` substitutes a placeholder, `allow` returns the real value. Every
    call is audited with the exact field list requested (not what happened to
    exist, or what policy let through) plus the denied/masked subsets — the
    read attempt itself is the sensitive act."""
    requested = [f for f in field_paths if f not in _NEVER_RETURNED_FIELDS]
    row = _find_latest_patient_record(session, patient_id)
    if row is None:
        raise PatientNotFoundError(f"no ingested record for patient_id={patient_id}")
    record = decrypt_record(row)
    features = extract_features(record)
    present = [f for f in requested if f in features]
    effects = _RESOLVE_FIELD_EFFECTS_FN(session, actor_role, purpose, present)

    result: dict[str, Any] = {}
    denied: list[str] = []
    masked: list[str] = []
    for f in present:
        effect = effects.get(f, "deny")
        if effect == "allow":
            result[f] = features[f]
        elif effect == "mask":
            result[f] = _MASKED_PLACEHOLDER
            masked.append(f)
        else:
            denied.append(f)

    write_event(
        session,
        action="record_access",
        actor_id=actor_id,
        actor_role=actor_role,
        purpose=purpose,
        conversation_id=conversation_id,
        patient_id=patient_id,
        record_fields=requested,
        detail={"denied_fields": denied, "masked_fields": masked} if (denied or masked) else None,
    )
    return result
