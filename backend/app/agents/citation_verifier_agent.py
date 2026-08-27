"""Citation-verifier agent — the enforced grounding gate (ARCH §8.3, ARCH-015).

Does: for each claim segment run: (1) citation-resolves (was the cited chunk in
THIS turn's retrieval snapshot?), (2) quote-integrity (verbatim substring +
offsets), (3) entailment (lexical overlap + constrained model call),
(4) scope/wording (no directive phrasing, no dosing/population claims absent
from the quote). Produce the per-segment verdict; force partial-strip or
escalation per the §8.3 verdict policy.
Does NOT: rewrite content to make it pass; add citations.
Access: this turn's retrieval snapshot + candidate segments.
Tools: get_chunk, nli_support_check, resolve_citation, lexical_overlap, wording_scan.
"""

from __future__ import annotations

from app.agents.state import GraphState


def run(state: GraphState) -> GraphState:
    raise NotImplementedError("Phase 3 (ARCH-015, ARCH §8.3)")
