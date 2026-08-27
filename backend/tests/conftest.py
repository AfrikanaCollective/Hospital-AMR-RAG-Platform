"""Test config. Offline only — no DB / network / real models (CLAUDE.md §5)."""

from __future__ import annotations

import os

import pytest

# Keep the config import side-effect-free and offline.
os.environ.setdefault("EMBEDDING_BACKEND", "stub")
os.environ.setdefault("RERANKER_BACKEND", "stub")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def settings():
    from app.config import Settings

    return Settings(_env_file=None)  # type: ignore[call-arg]
