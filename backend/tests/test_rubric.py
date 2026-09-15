"""Rubric shape + multi-rater guard predicates (ARCH §14; PRD-040..PRD-043)."""

from __future__ import annotations

from app.rubric.domains import RUBRIC_DOMAIN_CODES, RUBRIC_DOMAINS
from app.rubric.workflow import can_archive, is_eligible_rater
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
