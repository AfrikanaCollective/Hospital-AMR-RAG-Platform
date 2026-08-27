"""No-fabrication validator for generated narratives (ARCH §15.1 step 5; PRD-061).

Every clinical entity mentioned in a generated question (symptoms, findings,
history, timeline, demographics, meds) must map to a field VALUE actually
present in the source record. Any unmapped entity => reject and regenerate
(up to QGEN_MAX_RETRIES). The validator report is stored in
generator_meta.validator_report.

Phase 2 implements entity extraction + mapping. `ValidatorReport` is the
contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidatorReport:
    ok: bool
    mapped_entities: list[str] = field(default_factory=list)
    unmapped_entities: list[str] = field(default_factory=list)
    notes: str | None = None


def validate_narrative(question_text: str, source_record: dict) -> ValidatorReport:
    raise NotImplementedError("Phase 2 (ARCH §15.1 step 5)")
