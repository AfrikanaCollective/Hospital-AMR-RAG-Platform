"""Retrieval agent (ARCH §10.2, §7)."""

from __future__ import annotations

from contextlib import contextmanager

import app.agents.retrieval_agent as ra


@contextmanager
def _fake_session_scope():
    yield None


def test_run_populates_retrieval_and_confidence(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(ra, "_SESSION_SCOPE", _fake_session_scope)

    def _fake_retrieve(query, **kwargs):  # noqa: ANN001, ARG001
        items = [{"chunk_id": "c1", "score": 0.9}]
        snapshot = {
            "confidence": {"top_score": 0.9, "supporting_count": 1, "low_confidence": False}
        }
        return items, snapshot

    monkeypatch.setattr(ra, "_RETRIEVE_FN", _fake_retrieve)

    state = {"query": "what does the guideline say about fever?"}
    out = ra.run(state)  # type: ignore[arg-type]
    assert out["retrieval"] == [{"chunk_id": "c1", "score": 0.9}]
    assert out["retrieval_confidence"]["low_confidence"] is False
