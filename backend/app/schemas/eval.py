"""Eval / auto-question models (PRD-060..PRD-073; ARCH §15, §16)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import ExpectedOutcome, Provenance


class GenerateQuestionsRequest(BaseModel):
    count: int = Field(gt=0, le=5000)
    composition: str = "60,20,20"  # well_supported,missing_info_expected,no_guideline_expected
    add_to_fixed_testset: bool = False
    seed: int | None = None


class EvalQuestion(BaseModel):
    id: str
    text: str
    provenance: Provenance
    expected_outcome: ExpectedOutcome | None = None  # set for auto-generated
    source_record_id: str | None = None
    target_guideline_ref: dict | None = None  # None for no_guideline_expected
    gold_relevant_chunks: list[str] = Field(default_factory=list)
    gold_citations: list[dict] = Field(default_factory=list)
    in_fixed_testset: bool = False
    generator_meta: dict | None = None  # {model_id, template_version, validator_report}


class EvalRunRequest(BaseModel):
    snapshot: str = "latest"
    fail_on_threshold_breach: bool = True


class EvalRunReport(BaseModel):
    run_id: str
    config_snapshot: dict
    corpus_snapshot_id: str
    # metrics broken out by expected_outcome and by provenance subset (PRD-073)
    retrieval: dict = Field(default_factory=dict)
    citation: dict = Field(default_factory=dict)
    expected_outcome_pass: dict = Field(default_factory=dict)
    scope_safety: dict = Field(default_factory=dict)  # must show 0 violations, 100% disclaimer
    by_provenance: dict = Field(default_factory=dict)  # {auto_generated: {...}, clinician_submitted: {...}}
    passed: bool = False
