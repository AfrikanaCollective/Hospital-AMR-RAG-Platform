"""Request-context + audit middleware (ARCH-034, ARCH-035; PRD-085, PRD-NFR-4).

Responsibilities (Phase 4 completes them):
- assign/propagate a request id (also passed to workers and agents),
- bind actor / role / purpose-of-use into the log + audit context,
- emit a coarse `audit_event` for the request lifecycle (fine-grained events
  for retrieval / record access / answers are emitted by their own modules).
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        settings = get_settings()
        req_id = request.headers.get(settings.request_id_header) or str(uuid.uuid4())
        request.state.request_id = req_id
        # TODO(Phase 4): resolve actor/role/purpose from auth dependency and
        # bind to structlog contextvars + open an audit lifecycle event.
        response: Response = await call_next(request)
        response.headers[settings.request_id_header] = req_id
        return response
