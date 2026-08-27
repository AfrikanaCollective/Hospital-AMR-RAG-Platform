"""Retrieval agent (ARCH §10.2, §7).

Does: build queries; hybrid search (dense + sparse) + RRF fusion + cross-encoder
rerank; assess confidence; detect conflicts; expand context.
Does NOT: read PHI; synthesize prose; decide the final answer.
Access: Qdrant guideline collections + corpus schema (read). NO PHI.
Tools: hybrid_search, rerank, expand_context, list_corpus_topics, get_chunk,
get_version_status.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 2/3 (ARCH §7, ARCH-003)")
