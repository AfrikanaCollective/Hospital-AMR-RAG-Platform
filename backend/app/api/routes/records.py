"""Patient-record read endpoints (PHI) (PRD-080, PRD-084; ARCH §4.2, ARCH-034).

GET /records/{patient_id}/fields                 -> field NAMES only (no values); from field_index
GET /records/{patient_id}?fields=a,b&purpose=... -> authorized field VALUES only

Every access is field-level policy checked (`record_field_policy(role, purpose,
field_path)`) and audit-logged with the exact field list. Purpose-of-use header
required. RLS restricts rows to the caller's patient scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import Principal, current_principal, purpose_of_use

router = APIRouter()


@router.get("/{patient_id}/fields", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_fields(
    patient_id: str,
    _principal: Principal = Depends(current_principal),
    _purpose: str = Depends(purpose_of_use),
) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 2: field_index (ARCH §4.2).")


@router.get("/{patient_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_fields(
    patient_id: str,
    fields: str,
    _principal: Principal = Depends(current_principal),
    _purpose: str = Depends(purpose_of_use),
) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Phase 2/4: field-level access control + decryption (ARCH-034, ARCH-032).",
    )
