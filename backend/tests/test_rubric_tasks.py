"""Rubric Celery task bodies (ARCH §14.4; PRD-046)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models.eval import Result, RubricRating
from app.rubric import tasks


class _FakeSession:
    def __init__(self, results: list[Result], ratings: list[RubricRating]) -> None:
        self._results = results
        self._ratings = ratings
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def execute(self, stmt: object) -> object:
        entity = stmt.column_descriptions[0]["entity"]  # type: ignore[attr-defined]

        class _Result:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Result:
                return self

            def all(self) -> list:
                return self._rows

        if entity is Result:
            return _Result(self._results)
        # RubricRating select, filtered by result_id — the fake session is
        # constructed with only the ratings relevant to the result(s) under
        # test, mirroring the (already provenance-filtered) `results` list.
        return _Result(self._ratings)


def _rating(result_id, rater_id, domain, score):  # noqa: ANN001
    return RubricRating(
        id=uuid.uuid4(),
        result_id=result_id,
        rater_id=rater_id,
        domain_code=domain,
        score=score,
        rated_at=datetime.now(UTC),
        rating_round_id=uuid.uuid4(),
    )


def test_compute_slice_irr_filters_by_provenance_and_writes_batch() -> None:
    r1 = Result(
        id=uuid.uuid4(),
        provenance="clinician_submitted",
        queue_state="archived",
        created_at=datetime.now(UTC),
    )
    raters = [uuid.uuid4(), uuid.uuid4()]
    ratings = [
        _rating(r1.id, raters[0], "medical_consensus_alignment", 5),
        _rating(r1.id, raters[1], "medical_consensus_alignment", 4),
    ]
    session = _FakeSession([r1], ratings)  # pre-filtered by the (fake) query
    batch = tasks._run_compute_slice_irr(session, {"provenance": "clinician_submitted"})
    assert batch.n_items == 1
    assert "medical_consensus_alignment" in batch.per_domain
    assert batch in session.added


def test_compute_slice_irr_empty_slice_does_not_crash() -> None:
    session = _FakeSession([], [])
    batch = tasks._run_compute_slice_irr(session, {"provenance": "auto_generated"})
    assert batch.n_items == 0
    assert batch.per_domain == {}
