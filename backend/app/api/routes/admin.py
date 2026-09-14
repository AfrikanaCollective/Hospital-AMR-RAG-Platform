"""Admin endpoints (PRD-086; ARCH-034, ARCH-035).

Users/roles, config visibility, corpus ops, audit access. Admin access to
patient-record PHI (via `/records/*`) requires a purpose and is audit-logged
(ARCH-034) — that's a property of *that* access path, not of reading this
endpoint. Reading `GET /audit` itself is not, in turn, given its own audit
event: ARCH §18's action taxonomy (query/retrieval/record_access/answer/
hitl_action/ingestion/config_change/login) has no category that actually fits
"an admin listed some audit rows" — nothing changed (`config_change` would be
wrong) and no PHI field was read (`record_access` would be wrong). Flagged,
not invented around (DEVIATIONS.md #93).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.audit.log import query_events, verify_chain
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


def _serialize_event(e) -> dict:  # noqa: ANN001
    # Deliberately excludes query_text_enc/response_text_enc: raw ciphertext,
    # not JSON-serializable and not useful without a decrypt step this
    # listing endpoint has no reason to perform.
    return {
        "id": e.id,
        "ts": e.ts.isoformat(),
        "actor_id": str(e.actor_id) if e.actor_id else None,
        "actor_role": e.actor_role,
        "purpose": e.purpose,
        "action": e.action,
        "conversation_id": str(e.conversation_id) if e.conversation_id else None,
        "patient_id": str(e.patient_id) if e.patient_id else None,
        "query_hash": e.query_hash,
        "retrieved": e.retrieved,
        "record_fields": e.record_fields,
        "model_id": e.model_id,
        "response_hash": e.response_hash,
        "grounding_summary": e.grounding_summary,
        "outcome": e.outcome,
        "detail": e.detail,
        "prev_hash": e.prev_hash,
        "row_hash": e.row_hash,
    }


@router.get("/audit")
async def query_audit(  # noqa: PLR0917 - FastAPI query params, never called positionally
    action: str | None = None,
    patient_id: str | None = None,
    actor_id: str | None = None,
    limit: int = 50,
    verify: bool = False,
    session: Session = Depends(get_db),
) -> dict:
    events = query_events(
        session,
        action=action,
        patient_id=uuid.UUID(patient_id) if patient_id else None,
        actor_id=uuid.UUID(actor_id) if actor_id else None,
        limit=limit,
    )
    result: dict = {"events": [_serialize_event(e) for e in events]}
    if verify:
        result["broken_chain_ids"] = verify_chain(session)
    return result
