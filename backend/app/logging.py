"""Structured logging with PHI redaction (PRD-089, PRD-NFR-4, ARCH-018).

Application logs MUST NOT contain PHI. This module configures structlog with a
redaction processor. Audit records (which may hold encrypted PHI text) go
through `app.audit.log`, never through this logger.

Phase 1: configuration shell. The redaction processor currently drops a small
set of known-sensitive keys; Phase 4 hardens it (field allow-list + value
scrubbing).
"""

from __future__ import annotations

import logging
from typing import Any

_SENSITIVE_KEYS = {
    "payload", "record", "mrn", "patient_record", "answer_text", "query_text",
    "content", "prompt", "completion", "field_values",
}


def _redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = "<redacted:phi>"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    try:
        import structlog
    except ImportError:  # skeleton fallback
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _redact,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )


def get_logger(name: str | None = None) -> Any:
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
