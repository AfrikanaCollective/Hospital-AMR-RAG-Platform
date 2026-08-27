"""Skeleton smoke tests — the app imports and the health route works."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_imports_and_health_ok() -> None:
    from app.main import app

    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}


def test_openapi_declares_query_and_rubric_routes() -> None:
    from app.main import app

    client = TestClient(app)
    spec = client.get("/api/openapi.json").json()
    paths = spec["paths"]
    assert "/api/query" in paths
    assert "/api/rubric/domains" in paths
    assert "/api/review-queue" in paths


def test_agent_graph_excludes_next_step_recommender() -> None:
    from app.agents.graph import NODES

    assert "next_step_recommender" not in NODES  # reserved name only (ARCH-026)
    assert "local_adaptation" in NODES  # stub node is present
