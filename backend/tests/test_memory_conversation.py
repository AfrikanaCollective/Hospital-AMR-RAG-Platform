"""Session conversation memory (ARCH §11; PRD-022)."""

from __future__ import annotations

import uuid

import app.audit.log as audit_log
import app.memory.conversation as conv
from app.db.models.memory import Conversation, Message

CONVERSATION_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass


def test_append_message_round_trips_through_get_conversation(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    msg = conv.append_message(
        session,
        CONVERSATION_ID,
        turn=1,
        role="assistant",
        content="Guideline X recommends X.",
        citations=[{"citation_id": "c1"}],
    )
    assert msg in session.added

    conversation_row = Conversation(id=CONVERSATION_ID, user_id=uuid.uuid4(), status="active")
    monkeypatch.setattr(conv, "_get_conversation_row", lambda s, cid: conversation_row)
    monkeypatch.setattr(conv, "_list_messages", lambda s, cid: [msg])

    result = conv.get_conversation(session, CONVERSATION_ID)
    assert result["status"] == "active"
    assert result["messages"][0]["content"] == "Guideline X recommends X."
    assert result["messages"][0]["citations"] == [{"citation_id": "c1"}]


def test_get_conversation_raises_when_missing(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(conv, "_get_conversation_row", lambda s, cid: None)
    import pytest

    with pytest.raises(conv.ConversationNotFoundError):
        conv.get_conversation(_FakeSession(), CONVERSATION_ID)


def test_different_conversation_cannot_decrypt_another_conversations_message(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(audit_log, "_fetch_last_row_hash", lambda session: None)
    session = _FakeSession()
    msg = conv.append_message(session, CONVERSATION_ID, turn=1, role="user", content="secret")

    other_conversation = Conversation(id=uuid.uuid4(), user_id=uuid.uuid4(), status="active")
    monkeypatch.setattr(conv, "_get_conversation_row", lambda s, cid: other_conversation)
    monkeypatch.setattr(conv, "_list_messages", lambda s, cid: [msg])

    import pytest
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        conv.get_conversation(session, other_conversation.id)


def test_message_model_smoke() -> None:
    m = Message(conversation_id=CONVERSATION_ID, turn=1, role="user", content_enc=b"x" * 20)
    assert m.role == "user"
