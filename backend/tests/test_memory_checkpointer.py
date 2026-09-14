"""LangGraph Postgres checkpointer wiring (ARCH §11; PRD-023; DEVIATIONS.md #82)."""

from __future__ import annotations

from app.memory.checkpointer import _to_psycopg_dsn, _with_search_path


def test_strips_sqlalchemy_driver_qualifier() -> None:
    url = "postgresql+psycopg://hrag_app:hrag_app_pw@postgres:5432/hospital_rag"
    assert _to_psycopg_dsn(url) == "postgresql://hrag_app:hrag_app_pw@postgres:5432/hospital_rag"


def test_plain_dsn_is_unchanged() -> None:
    url = "postgresql://hrag_app:hrag_app_pw@postgres:5432/hospital_rag"
    assert _to_psycopg_dsn(url) == url


def test_with_search_path_appends_options_query_param() -> None:
    dsn = "postgresql://hrag_app:hrag_app_pw@postgres:5432/hospital_rag"
    result = _with_search_path(dsn, "memory")
    assert result.startswith(dsn + "?options=")
    assert "search_path" in result


def test_with_search_path_appends_with_ampersand_if_query_present() -> None:
    dsn = "postgresql://hrag_app:hrag_app_pw@postgres:5432/hospital_rag?sslmode=require"
    result = _with_search_path(dsn, "memory")
    assert "&options=" in result
