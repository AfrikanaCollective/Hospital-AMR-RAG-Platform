"""`/eval/*` HTTP routes (PRD-060..PRD-073; ARCH §15, §16)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.api.routes.eval as eval_routes
from app.api.deps import Principal, current_principal, get_db
from app.db.models.eval import EvalQuestion, EvalRun
from app.main import app as fastapi_app


class _FakeSession:
    def __init__(
        self, questions: list[EvalQuestion] | None = None, runs: dict | None = None
    ) -> None:
        self._questions = questions or []
        self._runs = runs or {}

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return self._runs.get(pk)

    def execute(self, stmt: object) -> object:
        class _Res:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Res:
                return self

            def all(self) -> list:
                return self._rows

        return _Res(self._questions)


@pytest.fixture(autouse=True)
def _overrides():
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id="admin-1", roles=frozenset({"admin", "reviewer"}), is_clinician=False
    )
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_generate_questions_enqueues(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    monkeypatch.setattr(eval_routes.generate_questions, "delay", lambda **kw: captured.update(kw))
    resp = client.post(
        "/api/eval/questions/generate", json={"count": 30, "composition": "60,20,20"}
    )
    assert resp.status_code == 202
    assert captured["count"] == 30


def test_list_questions_filters(client: TestClient) -> None:
    q1 = EvalQuestion(
        id=uuid.uuid4(),
        text="q1",
        provenance="auto_generated",
        expected_outcome="well_supported",
        in_fixed_testset=True,
        created_at=datetime.now(UTC),
    )
    q2 = EvalQuestion(
        id=uuid.uuid4(),
        text="q2",
        provenance="clinician_submitted",
        expected_outcome=None,
        in_fixed_testset=False,
        created_at=datetime.now(UTC),
    )
    fastapi_app.dependency_overrides[get_db] = lambda: _FakeSession(questions=[q1, q2])
    resp = client.get("/api/eval/questions")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_start_run_enqueues(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    monkeypatch.setattr(eval_routes.run_harness_task, "delay", lambda **kw: captured.update(kw))
    resp = client.post("/api/eval/runs", params={"snapshot": "v1"})
    assert resp.status_code == 202
    assert captured["snapshot"] == "v1"


def test_get_run_report(client: TestClient) -> None:
    run_id = uuid.uuid4()
    run = EvalRun(
        id=run_id,
        snapshot_label="v1",
        report={"passed": True},
        passed=True,
        created_at=datetime.now(UTC),
    )
    fastapi_app.dependency_overrides[get_db] = lambda: _FakeSession(runs={run_id: run})
    resp = client.get(f"/api/eval/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["passed"] is True


def test_get_unknown_run_404(client: TestClient) -> None:
    # Deliberately NOT `= _FakeSession` (PLW0108 doesn't see this): FastAPI's
    # dependency_overrides introspects the override callable's own signature,
    # and `_FakeSession.__init__`'s `questions: list[EvalQuestion] | None`
    # param isn't a valid Pydantic field type, so passing the class directly
    # crashes route resolution. The lambda hides that signature from FastAPI.
    fastapi_app.dependency_overrides[get_db] = lambda: _FakeSession()  # noqa: PLW0108
    resp = client.get(f"/api/eval/runs/{uuid.uuid4()}")
    assert resp.status_code == 404
