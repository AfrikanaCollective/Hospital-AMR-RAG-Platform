"""Engine + session factory (ARCH-008, ARCH-034).

`session_scope(patient_scope=...)` sets the `app.current_patient_scope` GUC used
by row-level security policies on records.* and memory.patient_context. Phase 4
wires this into the API request context.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(patient_scope: str | None = None) -> Iterator[Session]:
    session = SessionLocal()
    try:
        if patient_scope is not None:
            session.execute(
                text("SELECT set_config('app.current_patient_scope', :s, true)"),
                {"s": patient_scope},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
