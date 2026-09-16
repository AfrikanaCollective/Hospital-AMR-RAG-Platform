"""Rubric shape + multi-rater guard predicates (ARCH §14; PRD-040..PRD-043)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.rubric.domains import RUBRIC_DOMAIN_CODES, RUBRIC_DOMAINS
from app.rubric.workflow import QueueCandidate, can_archive, is_eligible_rater, select_queue_items
from app.schemas.rubric import RUBRIC_DOMAIN_CODES as SCHEMA_CODES


def test_eleven_domains_with_four_required_and_the_named_four() -> None:
    assert len(RUBRIC_DOMAINS) == 11
    required = {d.code for d in RUBRIC_DOMAINS if d.required}
    assert required == {
        "medical_consensus_alignment",
        "extent_of_harm",
        "clear_communication",
        "local_context_understanding",
    }


def test_domain_codes_match_between_schema_and_reference() -> None:
    assert tuple(SCHEMA_CODES) == tuple(RUBRIC_DOMAIN_CODES)
    assert len(set(RUBRIC_DOMAIN_CODES)) == 11


def test_each_domain_has_five_anchors() -> None:
    for d in RUBRIC_DOMAINS:
        assert len(d.anchors) == 5
        assert all(a.strip() for a in d.anchors)


def test_distinct_rater_eligibility() -> None:
    assert is_eligible_rater(rater_id="r2", result_producer_id="r1", already_rated_by={"r1"})
    assert not is_eligible_rater(rater_id="r1", result_producer_id="r1", already_rated_by=set())
    assert not is_eligible_rater(rater_id="r2", result_producer_id="r1", already_rated_by={"r2"})


def test_archive_requires_three_distinct_raters_all_domains() -> None:
    assert not can_archive(distinct_rater_count=2, min_raters=3, all_domains_scored_by_each=True)
    assert not can_archive(distinct_rater_count=3, min_raters=3, all_domains_scored_by_each=False)
    assert can_archive(distinct_rater_count=3, min_raters=3, all_domains_scored_by_each=True)


def _candidate(rounds: int, *, age_seconds: int = 0) -> QueueCandidate:
    return QueueCandidate(
        result_id=uuid.uuid4(),
        distinct_rater_count=rounds,
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=age_seconds),
    )


def test_queue_offers_any_unrated_item_when_none_are_in_progress() -> None:
    a, b = _candidate(0), _candidate(0)
    selected = select_queue_items([a, b])
    assert {c.result_id for c in selected} == {a.result_id, b.result_id}


def test_queue_offers_only_in_progress_items_when_any_exist() -> None:
    """The stated rule: an item with 1-2 rounds already must be finished
    before a fresh (0-round) one may be started."""
    fresh = _candidate(0)
    one_round = _candidate(1)
    two_rounds = _candidate(2)
    selected = select_queue_items([fresh, one_round, two_rounds])
    assert {c.result_id for c in selected} == {one_round.result_id, two_rounds.result_id}
    assert fresh.result_id not in {c.result_id for c in selected}


def test_queue_returns_to_any_item_once_no_in_progress_ones_remain() -> None:
    only_fresh = [_candidate(0), _candidate(0)]
    selected = select_queue_items(only_fresh)
    assert len(selected) == 2


def test_queue_never_offers_a_three_plus_round_item() -> None:
    """Defensive: `list_queue_candidates` should already filter to `open`
    results (which archive at 3 rounds), but `select_queue_items` itself
    must not accidentally surface one if it ever received it."""
    three_rounds = _candidate(3)
    selected = select_queue_items([_candidate(1), three_rounds])
    assert three_rounds.result_id not in {c.result_id for c in selected}


def test_queue_orders_oldest_first_within_a_bucket() -> None:
    newer = _candidate(1, age_seconds=100)
    older = _candidate(1, age_seconds=0)
    selected = select_queue_items([newer, older])
    assert [c.result_id for c in selected] == [older.result_id, newer.result_id]


def test_queue_empty_when_no_candidates() -> None:
    assert select_queue_items([]) == []
