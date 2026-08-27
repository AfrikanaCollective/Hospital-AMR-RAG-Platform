"""Session conversation memory (ARCH §11; PRD-022).

Durable messages (with retrieved_chunk_ids + scores, citations, grounding
reports, HITL actions) in Postgres; active window / streaming partials in Redis
(TTL). A conversation is bound to <= 1 patient_id (PRD-NG-011). Phase 3.
"""

from __future__ import annotations


def append_message(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Phase 3")


def get_conversation(conversation_id: str) -> dict:
    raise NotImplementedError("Phase 3")
