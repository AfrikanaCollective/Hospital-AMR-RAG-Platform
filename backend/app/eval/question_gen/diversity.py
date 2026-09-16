"""Diversity filter (ARCH §15.1 step 7; DEVIATIONS.md #67, #113).

Rejects a newly generated narrative whose embedding is too similar to one
already accepted in the same generation run. `QGEN_DEDUP_THRESHOLD`
(`app.config.Settings.qgen_dedup_threshold`) existed as a config knob since
Phase 1 but nothing read it — step 7 was documented and left unimplemented
(DEVIATIONS.md #67, "needs a populated corpus to check against"). This is
plain, deterministic code, not a model call (CLAUDE.md §4 "determinism where
it matters"): the embedding call itself is the only model-adjacent step, and
it's the same `embed_texts` already used for guideline-chunk embedding.
"""

from __future__ import annotations

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def is_near_duplicate(
    candidate_embedding: list[float],
    accepted_embeddings: list[list[float]],
    *,
    threshold: float,
) -> bool:
    """True if `candidate_embedding` is at or above `threshold` cosine
    similarity to any embedding already accepted this run."""
    return any(cosine_similarity(candidate_embedding, e) >= threshold for e in accepted_embeddings)
