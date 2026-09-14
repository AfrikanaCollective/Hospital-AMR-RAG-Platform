"""Shared LangGraph state (ARCH §10.1).

Every node reads/writes a subset of this. Every node writes a checkpoint
(Postgres checkpointer) so long runs survive worker restarts and are
inspectable/resumable (PRD-023).
"""

from __future__ import annotations

from typing import Any, TypedDict

from app.schemas.enums import ObservedOutcome, ScopeLabel


class RetrievalItem(TypedDict):
    chunk_id: str
    score: float
    section_path: str | None
    section_number: str | None
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    document_id: str
    document_title: str
    document_version_id: str
    version_label: str
    effective_date: str | None
    version_status: str
    chunk_type: str
    text: str
    heading: str | None
    meta: dict[str, Any]  # includes criteria[] for chunk_type=criteria (ARCH §6 rule 4)


class GraphState(TypedDict, total=False):
    # request context
    conversation_id: str
    user_id: str
    roles: list[str]
    purpose: str
    patient_id: str | None
    request_id: str

    # query
    query: str
    hospital_constraint: str | None
    scope_label: ScopeLabel

    # patient path (SCOPE-2.*)
    required_field_paths: list[str]  # narrows patient_record_agent's fetch, when known
    patient_features: dict[str, Any]  # authorized fields only
    stage_classification: dict[str, Any] | None
    missing_info: list[dict[str, Any]]

    # retrieval
    retrieval: list[RetrievalItem]
    retrieval_confidence: dict[str, Any]  # top_score, supporting_count, low_confidence, conflict

    # synthesis + grounding
    candidate_segments: list[dict[str, Any]]
    candidate_citations: list[dict[str, Any]]
    grounding_report: dict[str, Any]

    # outcome
    escalation: dict[str, Any] | None
    final_answer: dict[str, Any] | None
    observed_outcome: ObservedOutcome
