"""Lazy-singleton compiled-graph invocation (ARCH §10.1; DEVIATIONS.md #94, #105).

Shared by the synchronous `/query` route and the async Celery task
(`app.agents.tasks.run_query`) so both build/invoke the graph the exact same
way. Each process that imports this module (the API process, a worker
process) gets its **own** process-local `_GRAPH` singleton — building the
graph opens a real Postgres checkpointer connection
(`app.memory.checkpointer.get_checkpointer`), so it must happen lazily, on
first real invocation, never at import time (tests must never open a real DB
connection just by importing a module, CLAUDE.md §5).

`new_turn_thread_id` (DEVIATIONS.md #105): the checkpointer's `thread_id`
must be unique **per graph run**, not per conversation. `conversation_id`
alone was used as `thread_id` until this was found to be a real, severe bug:
LangGraph's checkpointer persists the *whole* state dict per thread and
merges each new `invoke()`'s `initial_state` on top of whatever was last
checkpointed for that thread — so a second `/query` call in the same
conversation started from a state that *already* had `scope_label`,
`final_answer`, `candidate_segments`, etc. left over from the first turn.
`app.agents.orchestrator.run` tells its two intra-turn visits apart by
`"scope_label" not in state` (see that module's own docstring) — a check
that only works if the state is genuinely empty at the start of a turn. With
a conversation-scoped thread_id it was not: the orchestrator's very first
call on turn 2 already looked like the *second* visit of turn 1, so it
skipped scope classification and retrieval entirely and re-assembled turn
1's stale `candidate_segments` as if they answered the new question — the
graph never even looked at the new `query`. No interrupt/resume feature in
this codebase depends on a stable thread across multiple `invoke()` calls
(confirmed: `interrupt`/`get_state`/`update_state` are not used anywhere),
so scoping `thread_id` to one call is free of that trade-off. Durability
within a single turn (`app.memory.checkpointer`'s Postgres-backed resume
across a crash mid-run) is unaffected — each turn still gets its own
consistent, inspectable stream of checkpoint rows, just no longer shared
with any other turn's.
"""

from __future__ import annotations

import uuid
from typing import Any

_GRAPH: Any = None


def new_turn_thread_id(conversation_id: str) -> str:
    """A fresh checkpointer thread id for one graph run — `conversation_id`
    stays as a readable prefix (for inspecting `memory.langgraph_checkpoint`
    rows by conversation) but never doubles as the thread key itself."""
    return f"{conversation_id}:{uuid.uuid4()}"


def invoke_graph(initial_state: dict, thread_id: str) -> dict:
    global _GRAPH  # noqa: PLW0603 - process-lifetime singleton; see module docstring
    if _GRAPH is None:
        from app.agents.graph import build_graph  # noqa: PLC0415

        _GRAPH = build_graph()
    return _GRAPH.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})
