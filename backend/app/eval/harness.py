"""Eval harness runner (ARCH §16; PRD-072, PRD-073).

Runs the pipeline over the fixed synthetic test set against a PINNED config
(model ids, thresholds, embedding_collection, corpus snapshot). Report is
broken out BY expected_outcome AND SEPARATELY for auto_generated vs
clinician_submitted (never a single pooled headline for the safety metrics).
CI fails on: any scope_boundary_violation, disclaimer < 100%,
no_guideline_expected pass < 100%, or sub-threshold retrieval/citation metrics.

Phase 3 implements.
"""

from __future__ import annotations

from app.schemas.eval import EvalRunReport


def run_harness(snapshot: str = "latest", *, fail_on_threshold_breach: bool = True) -> EvalRunReport:
    raise NotImplementedError("Phase 3 (ARCH §16)")
