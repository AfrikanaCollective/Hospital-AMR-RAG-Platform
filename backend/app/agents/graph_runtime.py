"""Lazy-singleton compiled-graph invocation (ARCH §10.1; DEVIATIONS.md #94).

Shared by the synchronous `/query` route and the async Celery task
(`app.agents.tasks.run_query`) so both build/invoke the graph the exact same
way. Each process that imports this module (the API process, a worker
process) gets its **own** process-local `_GRAPH` singleton — building the
graph opens a real Postgres checkpointer connection
(`app.memory.checkpointer.get_checkpointer`), so it must happen lazily, on
first real invocation, never at import time (tests must never open a real DB
connection just by importing a module, CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Any

_GRAPH: Any = None


def invoke_graph(initial_state: dict, thread_id: str) -> dict:
    global _GRAPH  # noqa: PLW0603 - process-lifetime singleton; see module docstring
    if _GRAPH is None:
        from app.agents.graph import build_graph  # noqa: PLC0415

        _GRAPH = build_graph()
    return _GRAPH.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})
