"""Admin endpoints (PRD-086; ARCH-034).

Users/roles, config visibility, corpus ops, audit access (itself audited).
Phase 4 implements. Admin access to PHI requires a purpose and is audit-logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role
from app.config import get_settings

router = APIRouter(dependencies=[Depends(require_role("admin"))])


@router.get("/config")
async def get_config_summary() -> dict[str, object]:
    s = get_settings()
    # Non-secret surface only.
    return {
        "app_env": s.app_env,
        "auth_provider": s.auth_provider,
        "secrets_backend": s.secrets_backend,
        "model_id_placeholder": s.is_model_placeholder(),
        "model_id_verified": s.model_id_verified,
        "embedding_backend": s.embedding_backend,
        "reranker_backend": s.reranker_backend,
        "patient_record_vectors_enabled": s.patient_record_vectors_enabled,
        "local_adaptation_enabled": s.local_adaptation_enabled,
        "irr_min_raters": s.irr_min_raters,
        "qgen_composition": s.qgen_composition,
    }


@router.get("/audit", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def query_audit() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Phase 4: audit access (ARCH-035).")
