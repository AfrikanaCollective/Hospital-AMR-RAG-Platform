"""Tool registry + per-agent allow-list enforcement (ARCH §10, ARCH-034).

A node may only call tools in its allow-list. `call_tool()` checks the calling
node id against `AGENT_TOOLS` before dispatch and raises on violation — this is
a security control, not a convenience.
"""

from __future__ import annotations

from collections.abc import Callable

# Per ARCHITECTURE.md §10.2. Keep in sync with that table.
AGENT_TOOLS: dict[str, frozenset[str]] = {
    "orchestrator": frozenset(
        {"classify_scope", "dispatch", "assemble_response", "apply_disclaimer", "open_escalation"}
    ),
    "retrieval": frozenset(
        {"hybrid_search", "rerank", "expand_context", "list_corpus_topics",
         "get_chunk", "get_version_status"}
    ),
    "patient_record": frozenset({"list_record_fields", "get_patient_fields"}),
    "stage_classifier": frozenset(
        {"hybrid_search", "get_chunk", "evaluate_criteria", "emit_classification"}
    ),
    "missing_info": frozenset(
        {"list_record_fields", "get_patient_fields", "get_chunk", "emit_missing_info"}
    ),
    "guideline_synthesis": frozenset({"get_chunk", "get_citation_metadata"}),
    "citation_verifier": frozenset(
        {"get_chunk", "nli_support_check", "resolve_citation", "lexical_overlap", "wording_scan"}
    ),
    "escalation": frozenset({"create_escalation", "enqueue_review", "notify_reviewers"}),
    "local_adaptation": frozenset(),  # STUB — no tools
    "next_step_recommender": frozenset(),  # RESERVED — not in the runtime graph
}

_REGISTRY: dict[str, Callable[..., object]] = {}


def register_tool(name: str, fn: Callable[..., object]) -> None:
    _REGISTRY[name] = fn


def call_tool(agent: str, tool: str, /, *args: object, **kwargs: object) -> object:
    allowed = AGENT_TOOLS.get(agent)
    if allowed is None:
        raise KeyError(f"unknown agent: {agent!r}")
    if tool not in allowed:
        raise PermissionError(f"agent {agent!r} may not call tool {tool!r} (ARCH-034)")
    if tool not in _REGISTRY:
        raise NotImplementedError(f"tool {tool!r} not implemented yet")
    return _REGISTRY[tool](*args, **kwargs)
