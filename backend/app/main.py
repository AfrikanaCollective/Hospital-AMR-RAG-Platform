"""FastAPI application factory (ARCH-001, ARCH-034, ARCH-037; PRD-100).

Phase 1: wires the router, config validation, logging, and the audit/request-id
middleware placeholder. Endpoint bodies are stubs (HTTP 501) until Phase 2+.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import RequestContextMiddleware
from app.api.router import api_router
from app.config import get_settings
from app.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Constraint #6: warn on unverified/placeholder model config at startup.
    # The answer path re-checks with require_answer_path=True before serving.
    settings.validate_model_config(require_answer_path=False)
    logger.info(
        "startup", app_env=settings.app_env, model_placeholder=settings.is_model_placeholder()
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Hospital RAG Platform API",
        version="0.1.0",
        description=(
            "Grounded, cited answers over clinical guidelines. Does NOT generate "
            "diagnoses, treatment plans, or independent clinical recommendations "
            "(see CDS-FUTURE.md). All patient data is synthetic."
        ),
        docs_url=f"{settings.api_base_path}/docs",
        openapi_url=f"{settings.api_base_path}/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix=settings.api_base_path)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
