"""Hybrid retrieval pipeline (ARCH §7).

1. query construction (curated abbreviation expansion only — never invent
   clinical content),
2. dense + sparse search in Qdrant with access filter,
3. RRF fusion (k = RRF_K),
4. cross-encoder rerank -> TOP_K,
5. confidence assessment (RETRIEVAL_MIN_SCORE / MIN_SUPPORTING_CHUNKS),
6. conflict detection (multi-version same-topic / NLI contradiction),
7. optional context expansion,
8. return ranked items + confidence/conflict verdict; caller writes
   retrieval_snapshot + audit_event.retrieved.

Phase 2 implements.
"""

from __future__ import annotations

from app.agents.state import RetrievalItem


def retrieve(query: str, *, access_filter: dict | None = None) -> tuple[list[RetrievalItem], dict]:
    raise NotImplementedError("Phase 2 (ARCH §7)")
