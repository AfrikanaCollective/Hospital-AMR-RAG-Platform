"""Top-level API router (ARCH-001). See ARCHITECTURE.md §2, §12–§16."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    conversations,
    corpus,
    eval as eval_routes,
    health,
    hitl,
    ingest,
    query,
    records,
    review_queue,
    rubric,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
api_router.include_router(corpus.router, prefix="/corpus", tags=["corpus"])
api_router.include_router(records.router, prefix="/records", tags=["records"])
api_router.include_router(hitl.router, prefix="/hitl", tags=["hitl"])
api_router.include_router(review_queue.router, prefix="/review-queue", tags=["review"])
api_router.include_router(rubric.router, prefix="/rubric", tags=["rubric"])
api_router.include_router(eval_routes.router, prefix="/eval", tags=["eval"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
