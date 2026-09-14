"""`/rubric/*` HTTP routes (PRD-040..PRD-044; ARCH §14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Principal, current_principal, get_db
from app.db.models.eval import IRRScore, RatingRound, Result, RubricRating
from app.main import app as fastapi_app
from app.rubric.domains import RUBRIC_DOMAIN_CODES

RESULT_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self) -> None:
        self.result = Result(
            id=RESULT_ID,
            provenance="clinician_submitted",
            queue_state="not_queued",
            created_at=datetime.now(UTC),
        )
        self.rounds: list[RatingRound] = []
        self.ratings: list[RubricRating] = []
        self.irr: list[IRRScore] = []

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return self.result if pk == self.result.id else None

    def add(self, obj: object) -> None:
        if isinstance(obj, RatingRound):
            self.rounds.append(obj)
        elif isinstance(obj, RubricRating):
            self.ratings.append(obj)
        elif isinstance(obj, IRRScore):
            self.irr.append(obj)

    def flush(self) -> None:
        for obj in self.rounds:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def execute(self, stmt: object) -> object:
        entity = stmt.column_descriptions[0]["entity"]  # type: ignore[attr-defined]

        class _Res:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Res:
                return self

            def all(self) -> list:
                return self._rows

        table = {RatingRound: self.rounds, RubricRating: self.ratings, IRRScore: self.irr}
        return _Res(table[entity])


@pytest.fixture(autouse=True)
def _overrides():
    session = _FakeSession()
    fastapi_app.dependency_overrides[get_db] = lambda: session
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=str(uuid.uuid4()), roles=frozenset({"reviewer"}), is_clinician=True
    )
    yield session
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_list_domains_returns_eleven() -> None:
    resp = TestClient(fastapi_app).get("/api/rubric/domains")
    assert resp.status_code == 200
    assert len(resp.json()) == len(RUBRIC_DOMAIN_CODES)


def test_submit_rating_requires_all_domains(client: TestClient) -> None:
    resp = client.post(
        f"/api/rubric/results/{RESULT_ID}/ratings",
        json={"scores": [{"domain_code": "accuracy", "score": 5}]},
    )
    assert resp.status_code == 422


def test_submit_rating_opens_queue(client: TestClient) -> None:
    scores = [{"domain_code": c, "score": 4} for c in RUBRIC_DOMAIN_CODES]
    resp = client.post(f"/api/rubric/results/{RESULT_ID}/ratings", json={"scores": scores})
    assert resp.status_code == 200
    assert "rating_round_id" in resp.json()


def test_submit_rating_unknown_result_404(client: TestClient) -> None:
    scores = [{"domain_code": c, "score": 4} for c in RUBRIC_DOMAIN_CODES]
    resp = client.post(f"/api/rubric/results/{uuid.uuid4()}/ratings", json={"scores": scores})
    assert resp.status_code == 404


def test_get_result_ratings_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    resp = client.get(f"/api/rubric/results/{RESULT_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == str(RESULT_ID)
    assert body["distinct_rater_count"] == 0
    assert body["archived"] is False
