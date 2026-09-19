"""Query-augmentation builders for Arm B (criteria-reuse) and Arm C
(operator-vocabulary) of the orchestration ablation (PRD-111;
PHASE7-PROPOSAL.md §2). Both only ever add vocabulary to a *retrieval*
query — neither can appear in or support answer text, so grounding is
unaffected (PHASE7-PROPOSAL.md §7).

**Source records: synthetic only, no PHI (PHASE7-PROPOSAL.md §7).**
`EvalQuestion.source_record_id` is populated by two different pipelines —
`app.eval.tasks.generate_questions` (bundled `synthetic-generator-v1`
records, `source_record_id` = a deterministic `uuid5` hash of the record's
own `record_id` string) and `app.eval.auto_seed` (real, attested
de-identified records, `source_record_id` = a real `records.patient.id`).
This module resolves `source_record_id` **only** via the first path — a
reverse `uuid5` lookup against the bundled synthetic JSON file, never a
`records.patient`/`records.patient_record` DB read. A `source_record_id`
that doesn't resolve (a de-identified-sourced question, or none at all)
simply yields no record, and both arms degrade to Arm A for that question
(§3's documented "no match" case) — never an attempt to reach PHI.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.agents.state import RetrievalItem
from app.config import get_settings
from app.eval.tasks import _RECORD_ID_NAMESPACE, _load_synthetic_records
from app.records.access import extract_features
from app.records.concepts import ConceptVocabulary, build_expansion_term, evaluate_concepts
from app.records.criteria import evaluate_criteria
from app.schemas.record import PatientRecord


def load_synthetic_record_index(records_dir: str | None = None) -> dict[uuid.UUID, dict[str, Any]]:
    """`uuid5(record_id)` -> raw `PatientRecord`-shaped dict, for every
    bundled synthetic record — the same hash `app.eval.tasks.generate_questions`
    uses to set `EvalQuestion.source_record_id`."""
    directory = records_dir if records_dir is not None else get_settings().patient_records_dir
    index: dict[uuid.UUID, dict[str, Any]] = {}
    for record in _load_synthetic_records(directory):
        record_id = record.get("record_id")
        if record_id is None:
            continue
        index[uuid.uuid5(_RECORD_ID_NAMESPACE, str(record_id))] = record
    return index


def resolve_source_record(
    source_record_id: uuid.UUID | str | None, index: dict[uuid.UUID, dict[str, Any]]
) -> PatientRecord | None:
    """`None` for a question with no source record, or one that doesn't
    resolve against the synthetic index (a de-identified-sourced question —
    deliberately never looked up any other way, see module docstring)."""
    if source_record_id is None:
        return None
    key = (
        source_record_id
        if isinstance(source_record_id, uuid.UUID)
        else uuid.UUID(str(source_record_id))
    )
    raw = index.get(key)
    if raw is None:
        return None
    return PatientRecord.model_validate(raw)


@dataclass(frozen=True)
class AugmentedQuery:
    text: str
    fired: bool  # did augmentation actually change the query from the raw question?


def build_arm_b_query(
    question_text: str, pass1_items: list[RetrievalItem], record: PatientRecord | None
) -> AugmentedQuery:
    """Arm B (criteria-reuse): augment with criteria already retrieved in
    pass 1 that the patient's own record actually matches (PHASE7-PROPOSAL.md
    §2). Every clause traces to a chunk retrieved for this same question —
    never an invented fact."""
    if record is None:
        return AugmentedQuery(text=question_text, fired=False)
    features = extract_features(record)
    clauses: list[str] = []
    for item in pass1_items:
        if item.get("chunk_type") != "criteria":
            continue
        criteria = (item.get("meta") or {}).get("criteria") or []
        for match in evaluate_criteria(criteria, features):
            if match.matched:
                c = match.criterion
                clause = (
                    f"{c.get('field', '')} {c.get('operator', '')} {c.get('value', '')}".strip()
                )
                clauses.append(clause)
    if not clauses:
        return AugmentedQuery(text=question_text, fired=False)
    return AugmentedQuery(text=f"{question_text}; {'; '.join(clauses)}", fired=True)


def build_arm_c_query(
    question_text: str, vocabulary: ConceptVocabulary, record: PatientRecord | None
) -> AugmentedQuery:
    """Arm C (operator-vocabulary): augment with operator-authored concept
    matches, computed before any retrieval (PHASE7-PROPOSAL.md §2)."""
    if record is None:
        return AugmentedQuery(text=question_text, fired=False)
    features = extract_features(record)
    matched = evaluate_concepts(vocabulary, features)
    if not matched:
        return AugmentedQuery(text=question_text, fired=False)
    terms = [build_expansion_term(c) for c in matched]
    return AugmentedQuery(text=f"{question_text}; {'; '.join(terms)}", fired=True)
