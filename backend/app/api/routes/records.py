"""Patient-record read endpoints (PHI) (PRD-080, PRD-084; ARCH §4.2, ARCH-034).

GET /records/{patient_id}/fields  -> field NAMES only (no values); from field_index.
    Not `record_field_policy`-gated or audited: field *presence*, with no value
    attached, carries the same (lower) sensitivity as `missing_info_agent`'s
    `get_record_field_index` use, which is also ungated/unaudited — see
    `app.records.access` module docstring.
GET /records/{patient_id}?fields=a,b  (X-Purpose-Of-Use header required)
    -> authorized field VALUES only, gated per-field by
    `record_field_policy(role, purpose, field_path)` and audit-logged with the
    exact field list requested plus any denied/masked subsets.

Both routes are `clinician`-only (`ROUTE_PERMISSIONS["records:read"]`,
`app.auth.rbac`) and RLS-scoped to `{patient_id}`
(`app.api.deps.get_patient_scoped_db`, DEVIATIONS.md #88) — `require_role`
already guarantees the caller holds `clinician`, so `actor_role` for the
field-policy gate is unambiguously `"clinician"`, no `_select_actor_role`-style
disambiguation needed (contrast `patient_record_agent`, whose caller's role
set isn't route-restricted the same way).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import (
    Principal,
    get_patient_scoped_db,
    principal_uuid,
    purpose_of_use,
    require_role,
)
from app.records.access import PatientNotFoundError, get_patient_fields, list_record_fields

router = APIRouter()

_ROLE = "clinician"


@router.get("/{patient_id}/fields")
async def list_fields(
    patient_id: str,
    _principal: Principal = Depends(require_role(_ROLE)),
    session: Session = Depends(get_patient_scoped_db),
) -> list[str]:
    try:
        return list_record_fields(session, uuid.UUID(patient_id))
    except PatientNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/{patient_id}")
async def get_fields(
    patient_id: str,
    fields: str,
    principal: Principal = Depends(require_role(_ROLE)),
    purpose: str = Depends(purpose_of_use),
    session: Session = Depends(get_patient_scoped_db),
) -> dict[str, Any]:
    field_paths = [f.strip() for f in fields.split(",") if f.strip()]
    try:
        return get_patient_fields(
            session,
            uuid.UUID(patient_id),
            field_paths,
            purpose=purpose,
            actor_role=_ROLE,
            actor_id=principal_uuid(principal),
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
