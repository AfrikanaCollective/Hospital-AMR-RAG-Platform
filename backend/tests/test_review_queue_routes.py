"""`/review-queue/*` HTTP routes (PRD-042, PRD-047; ARCH §14.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import Principal, current_principal, get_db
from app.db.models.eval import RatingRound, Result
from app.main import app as fastapi_app

RATER_ID = uuid.uuid4()


class _FakeSession:
    def __init__(self, results: list[Result], rounds: list[RatingRound]) -> None:
        self._results = results
        self._rounds = rounds

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return next((r for r in self._results if r.id == pk), None)

    def execute(self, stmt: object) -> object:
        descriptions = stmt.column_descriptions  # type: ignore[attr-defined]
        entity = descriptions[0]["entity"]

        class _Res:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Res:
                return self

            def all(self) -> list:
                return self._rows

        if entity is RatingRound:
            return _Res(self._rounds)
        if len(descriptions) > 1:
            # app.rubric.workflow.list_queue_candidates's tuple-select
            # (Result.id, Result.created_at, distinct rater count) — a
            # different shape from the whole-entity `select(Result)` below,
            # so it needs its own branch here. Replicates that function's
            # filters in plain Python: `queue_state == "open"`, excluding
            # anything the calling rater (RATER_ID — the only principal any
            # test in this module acts as) has already rated.
            already_rated = {rr.result_id for rr in self._rounds if rr.rater_id == RATER_ID}
            rows = [
                (
                    r.id,
                    r.created_at,
                    len({rr.rater_id for rr in self._rounds if rr.result_id == r.id}),
                )
                for r in self._results
                if r.queue_state == "open" and r.id not in already_rated
            ]
            return _Res(rows)
        # The only remaining (whole-entity) Result select in these routes
        # fetches by id, after `list_queue_candidates` has already filtered.
        return _Res([r for r in self._results if r.queue_state == "open"])


@pytest.fixture(autouse=True)
def _principal_override():
    fastapi_app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=str(RATER_ID), roles=frozenset({"reviewer"}), is_clinician=True
    )
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


def test_queue_excludes_already_rated_and_not_open(client: TestClient) -> None:
    open_result = Result(
        id=uuid.uuid4(),
        provenance="auto_generated",
        expected_outcome="well_supported",
        queue_state="open",
        created_at=datetime.now(UTC),
    )
    rated_result = Result(
        id=uuid.uuid4(),
        provenance="clinician_submitted",
        queue_state="open",
        created_at=datetime.now(UTC),
    )
    archived_result = Result(
        id=uuid.uuid4(),
        provenance="clinician_submitted",
        queue_state="archived",
        created_at=datetime.now(UTC),
    )
    already_rated_round = RatingRound(
        id=uuid.uuid4(),
        result_id=rated_result.id,
        rater_id=RATER_ID,
        submitted_at=datetime.now(UTC),
    )
    session = _FakeSession([open_result, rated_result, archived_result], [already_rated_round])
    fastapi_app.dependency_overrides[get_db] = lambda: session

    resp = client.get("/api/review-queue")
    assert resp.status_code == 200
    ids = {row["result_id"] for row in resp.json()}
    assert ids == {str(open_result.id)}


def test_get_queue_item_hides_other_raters_scores(client: TestClient) -> None:
    result = Result(
        id=uuid.uuid4(),
        provenance="auto_generated",
        queue_state="open",
        answer_enc=None,
        citations=[{"citation_id": "c1"}],
        grounding_report={"action": "release"},
        created_at=datetime.now(UTC),
    )
    session = _FakeSession([result], [])
    fastapi_app.dependency_overrides[get_db] = lambda: session

    resp = client.get(f"/api/review-queue/{result.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["citations"] == [{"citation_id": "c1"}]
    assert "scores" not in body
    assert "rater_id" not in body


def test_get_queue_item_not_queued_is_404(client: TestClient) -> None:
    result = Result(
        id=uuid.uuid4(),
        provenance="auto_generated",
        queue_state="not_queued",
        created_at=datetime.now(UTC),
    )
    session = _FakeSession([result], [])
    fastapi_app.dependency_overrides[get_db] = lambda: session

    resp = client.get(f"/api/review-queue/{result.id}")
    assert resp.status_code == 404
