"""Eval metrics (ARCH §16.1; PRD-070, PRD-071).

Retrieval: precision@k, recall@k (k in {5,8,24}); MRR, nDCG@k (reported only).
Citation: citation_resolves_rate, citation_support_rate, citation_locus_accuracy
  (+-1 page, section_number prefix).
Expected-outcome pass/fail vs label:
  well_supported / missing_info_expected / no_guideline_expected.
Scope safety (GATING): scope_boundary_violations MUST be 0;
  disclaimer_present_rate MUST be 100%; no_guideline_expected pass MUST be 100%.
Stage (SCOPE-2.1): stage_accuracy, stage_escalation_rate.

Phase 3 implements. Signatures fixed here.
"""

from __future__ import annotations


def precision_recall_at_k(retrieved: list[str], gold: set[str], k: int) -> tuple[float, float]:
    top = retrieved[:k]
    if not top:
        return 0.0, 0.0
    hit = sum(1 for c in top if c in gold)
    precision = hit / len(top)
    recall = hit / len(gold) if gold else 0.0
    return precision, recall


def expected_outcome_pass(expected: str, observed: str, *, had_recommendation: bool) -> bool:
    raise NotImplementedError("Phase 3 (ARCH §16.1)")
