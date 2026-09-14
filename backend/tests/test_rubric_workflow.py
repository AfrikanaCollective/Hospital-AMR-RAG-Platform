"""Multi-rater workflow (ARCH §14.2-§14.5; PRD-042, PRD-043, PRD-047)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

import app.rubric.workflow as wf
from app.config import get_settings
from app.db.models.eval import RatingRound, Result, RubricRating
from app.rubric.domains import RUBRIC_DOMAIN_CODES
from app.schemas.rubric import DomainScore

RESULT_ID = uuid.uuid4()
N_DOMAINS = len(RUBRIC_DOMAIN_CODES)


class _FakeSession:
    def __init__(self, result: Result) -> None:
        self._result = result
        self.rounds: list[RatingRound] = []
        self.ratings: list[RubricRating] = []
        self.archives: list = []
        self.irr_scores: list = []

    def get(self, model: object, pk: object) -> object:  # noqa: ARG002
        return self._result if pk == self._result.id else None

    def add(self, obj: object) -> None:
        if isinstance(obj, RatingRound):
            self.rounds.append(obj)
        elif isinstance(obj, RubricRating):
            self.ratings.append(obj)
        elif type(obj).__name__ == "ResultArchive":
            self.archives.append(obj)
        elif type(obj).__name__ == "IRRScore":
            self.irr_scores.append(obj)

    def flush(self) -> None:
        for obj in self.rounds:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def execute(self, stmt: object) -> object:
        entity = stmt.column_descriptions[0]["entity"]  # type: ignore[attr-defined]

        class _Result:
            def __init__(self, rows: list) -> None:
                self._rows = rows

            def scalars(self) -> _Result:
                return self

            def all(self) -> list:
                return self._rows

        return _Result(self.rounds if entity is RatingRound else self.ratings)


def _full_scores(base: int = 4) -> list[DomainScore]:
    return [DomainScore(domain_code=c, score=base) for c in RUBRIC_DOMAIN_CODES]


def _result() -> Result:
    return Result(
        id=RESULT_ID,
        provenance="clinician_submitted",
        queue_state="not_queued",
        created_at=datetime.now(UTC),
    )


def test_first_rating_opens_the_queue() -> None:
    result = _result()
    session = _FakeSession(result)
    wf.submit_rating(session, result_id=RESULT_ID, rater_id=uuid.uuid4(), scores=_full_scores())
    assert result.queue_state == "open"
    assert len(session.ratings) == N_DOMAINS


def test_duplicate_rater_rejected() -> None:
    result = _result()
    session = _FakeSession(result)
    rater = uuid.uuid4()
    wf.submit_rating(session, result_id=RESULT_ID, rater_id=rater, scores=_full_scores())
    with pytest.raises(wf.DuplicateRaterError):
        wf.submit_rating(session, result_id=RESULT_ID, rater_id=rater, scores=_full_scores())


def test_unknown_result_raises() -> None:
    session = _FakeSession(_result())
    with pytest.raises(wf.ResultNotFoundError):
        wf.submit_rating(
            session, result_id=uuid.uuid4(), rater_id=uuid.uuid4(), scores=_full_scores()
        )


def test_third_distinct_rater_triggers_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IRR_MIN_RATERS", "3")
    get_settings.cache_clear()
    result = _result()
    session = _FakeSession(result)
    wf.submit_rating(session, result_id=RESULT_ID, rater_id=uuid.uuid4(), scores=_full_scores(4))
    assert result.queue_state == "open"
    wf.submit_rating(session, result_id=RESULT_ID, rater_id=uuid.uuid4(), scores=_full_scores(4))
    assert result.queue_state == "open"
    wf.submit_rating(session, result_id=RESULT_ID, rater_id=uuid.uuid4(), scores=_full_scores(5))
    assert result.queue_state == "archived"
    assert len(session.irr_scores) == N_DOMAINS
    assert len(session.archives) == 1
    get_settings.cache_clear()
