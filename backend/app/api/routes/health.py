"""Health / readiness (PRD-G7)."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, object]:
    s = get_settings()
    # Phase 4: probe postgres / redis / qdrant / gateway.
    return {
        "status": "ok",
        "model_id_placeholder": s.is_model_placeholder(),
        "model_id_verified": s.model_id_verified,
        "embedding_backend": s.embedding_backend,
    }
