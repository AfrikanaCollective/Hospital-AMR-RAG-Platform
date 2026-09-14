"""Rubric / rating models (PRD-040, PRD-041; ARCH §14).

Scores are structured (domain, score 1-5, rater, timestamp, result) — never
free text. `comment` is an optional adjunct, not a substitute.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.enums import HitlAcceptAction

RUBRIC_DOMAIN_CODES: tuple[str, ...] = (
    "accuracy",
    "groundedness",
    "completeness",
    "safety",
    "scope_adherence",
    "contextual_appropriateness",
    "clarity",
    "relevance",
    "uncertainty_handling",
    "missing_info_handling",
    "bias_equity",
)


class DomainScore(BaseModel):
    domain_code: str
    score: int = Field(ge=1, le=5)

    @field_validator("domain_code")
    @classmethod
    def _known_domain(cls, v: str) -> str:
        if v not in RUBRIC_DOMAIN_CODES:
            raise ValueError(f"unknown rubric domain: {v}")
        return v


class RatingRoundRequest(BaseModel):
    """One clinician's independent pass over one result (ARCH §14.2).

    Both HITL axes are captured together in this one sitting (ARCH §13.2
    "Both axes together"; `rating_round.accept_action_id` links the two rows
    this produces): a rater completing a case's 11-domain rubric always also
    records an accept-axis decision for it — `accept_action` is required, not
    optional, on every submission. That is the whole of a ranker's task —
    exactly two things, the rubric and the accept-axis pick (DEVIATIONS.md
    #100, #101): no reason/justification text and no edited-answer text is
    collected here — a ranker is never required to write anything, only to
    score and pick — and submitting a rating never creates or touches a
    `hitl.escalation` row (`apply_rating_accept_action` always sets
    `escalation_id=None`).
    """

    scores: list[DomainScore] = Field(
        min_length=len(RUBRIC_DOMAIN_CODES), max_length=len(RUBRIC_DOMAIN_CODES)
    )
    comment: str | None = None
    accept_action: HitlAcceptAction
    # Optional (DEVIATIONS.md #101): a ranker may still volunteer edited text,
    # but partial_accept never requires it — accept_accepted_context_ids
    # alone is a complete, valid partial_accept.
    accept_edited_answer: str | None = None
    accept_accepted_context_ids: list[str] = Field(default_factory=list)

    @field_validator("scores")
    @classmethod
    def _all_domains_once(cls, v: list[DomainScore]) -> list[DomainScore]:
        codes = [s.domain_code for s in v]
        if sorted(codes) != sorted(RUBRIC_DOMAIN_CODES):
            raise ValueError("exactly one score per rubric domain is required")
        return v


class IRRDomainScore(BaseModel):
    domain_code: str | None  # None = aggregate/overall
    metric: str  # e.g. "krippendorff_alpha_ordinal"
    value: float
    n_raters: int
    n_items: int


class ResultRatingSummary(BaseModel):
    result_id: str
    provenance: str
    expected_outcome: str | None
    distinct_rater_count: int
    archived: bool
    rounds: list[dict] = Field(default_factory=list)
    irr: list[IRRDomainScore] = Field(default_factory=list)
    last_updated: datetime | None = None
