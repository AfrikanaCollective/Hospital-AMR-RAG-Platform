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

A kept claim segment's `citation_ids` is narrowed to the verified subset
before it's ever returned (DEVIATIONS.md #107): a segment is SUPPORTED/WEAK
if ANY of its cited ids has a chunk containing the quote — a model
frequently over-cites, listing two or three plausible sources per claim when
only one actually contains the quote — but the *un*verified ids among them
must not survive into the final answer, or the UI renders a footnote link
(`[c2]`) with no citation object behind it, and the citations list under-
counts what the answer text appears to reference.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from app.agents.state import GraphState
from app.grounding.verifier import citations_for_segments, verify
from app.llm.gateway import LLMGateway
from app.schemas.enums import EscalationTrigger

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_nli_template() -> str:
    return (_PROMPTS_DIR / "citation_verifier.md").read_text()


def _gateway_entailment_fn(gateway: LLMGateway) -> Callable[[str, str], str]:
    template = _load_nli_template()

    def _fn(claim: str, quote: str) -> str:
        prompt = template.replace("{{claim}}", claim).replace("{{passage}}", quote)
        result = gateway.chat(system="", messages=[{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", result.text, re.DOTALL)
        if not match:
            return "no"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return "no"
        verdict = str(data.get("verdict", "no")).lower()
        return verdict if verdict in ("yes", "no", "partly") else "no"

    return _fn


# Indirection point for tests (avoids constructing a real LLMGateway, which
# requires a non-placeholder MODEL_ID): monkeypatch to a fake
# Callable[[str, str], str] or leave None to force lexical-only entailment.
_ENTAILMENT_FN: Callable[[str, str], str] | None = None


def _resolve_entailment_fn() -> Callable[[str, str], str] | None:
    if _ENTAILMENT_FN is not None:
        return _ENTAILMENT_FN
    try:
        return _gateway_entailment_fn(LLMGateway())
    except Exception:  # noqa: BLE001 - no usable gateway configured: fall back to lexical-only
        return None


def run(state: GraphState) -> GraphState:
    if state.get("escalation"):
        # Already decided upstream (see guideline_synthesis_agent's matching
        # guard) — nothing to verify.
        return state
    if state.get("observed_outcome") is not None:
        # A terminal no-guideline / out-of-scope framing-only answer: no
        # claims were made, so there is nothing for the grounding gate to
        # check (and no citations to build).
        return state

    segments = state.get("candidate_segments") or []
    snapshot = [dict(item) for item in state.get("retrieval") or []]

    report = verify(segments, snapshot, entailment_fn=_resolve_entailment_fn())
    state["grounding_report"] = {
        "action": report.action,
        "stripped_segment_indexes": report.stripped_segment_indexes,
        "per_segment": [
            {"segment_index": v.segment_index, "verdict": v.verdict.value, "reason": v.reason}
            for v in report.per_segment
        ],
    }

    if report.action == "escalate":
        scope_violation = any(v.reason == "scope_violation" for v in report.per_segment)
        state["escalation"] = {
            "trigger_code": EscalationTrigger.SAFETY_FILTER
            if scope_violation
            else EscalationTrigger.GROUNDING_FAILURE,
            "message": (
                "This response could not be safely grounded in the retrieved guideline "
                "text and needs clinician review."
            ),
        }
        return state

    stripped = set(report.stripped_segment_indexes)
    verdicts_by_index = {v.segment_index: v for v in report.per_segment}
    kept_segments = []
    for i, seg in enumerate(segments):
        if i in stripped:
            continue
        verdict = verdicts_by_index.get(i)
        kept = seg
        if verdict and verdict.verified_citation_ids is not None:
            # DEVIATIONS.md #107: a segment is kept if ANY of its cited ids
            # verifies, not all — narrow to just the ones that actually do,
            # so a released segment never references a citation_id nothing
            # downstream builds a Citation for (a dangling footnote link).
            kept = {**seg, "citation_ids": verdict.verified_citation_ids}
        kept_segments.append(kept)
    citations = citations_for_segments(kept_segments, snapshot)
    state["candidate_segments"] = kept_segments
    state["candidate_citations"] = [c.model_dump(mode="json") for c in citations.values()]
    return state
