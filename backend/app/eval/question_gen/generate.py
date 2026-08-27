"""Narrative generation (ARCH §15.1 steps 2-6; PRD-060, PRD-061, PRD-064).

- pick a source record (for missing_info_expected: null out required fields;
  for no_guideline_expected: a scenario the corpus does not cover),
- extract a field subset actually present,
- generate a scope-1-framed narrative via LLMGateway (MODEL_ID), low temp,
  fixed template (records template_version),
- validate grounding of the narrative (app.eval.question_gen.validate),
- label + persist an eval_question,
- diversity filter (embedding cosine < QGEN_DEDUP_THRESHOLD; min distinct topics),
- gold re-check for no_guideline_expected.

Phase 2 implements.
"""

from __future__ import annotations

from app.schemas.enums import ExpectedOutcome


def generate_question(source_record: dict, expected: ExpectedOutcome) -> dict:
    raise NotImplementedError("Phase 2 (ARCH §15.1)")
