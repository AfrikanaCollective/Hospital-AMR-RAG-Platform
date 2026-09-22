"""Unified hierarchical ablation (PRD-112 / ARCH-043).

Streamlines `app.eval.model_ablation`, `app.eval.orchestration_ablation`,
and `app.eval.retrieval_tuning` into one nested Level-1 (clinical-sign
query construction) x Level-2 (vocabulary/concept enrichment) x Level-3
(retrieval/embedding strategy) experiment, evaluated per query so all 16
leaf configurations can be paired-compared for the same query. See
UNIFIED-ABLATION-PROPOSAL.md at the repo root for the full design.

Additive and independently executable: this package changes nothing about
the three pre-existing ablation modules (beyond the shared, behavior-
identical `app.eval.bootstrap`/`offline_fusion.min_max_normalize`
promotions, DEVIATIONS.md #192) or `app.retrieval.hybrid.retrieve()`
(the real `/query` path).
"""

from __future__ import annotations
