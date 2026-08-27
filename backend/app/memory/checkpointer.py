"""LangGraph Postgres checkpointer wiring (ARCH §11; PRD-023).

Long agent runs are checkpointed so they survive worker restarts and can be
inspected/resumed. A checkpoint tied to an open escalation is retained until
the escalation resolves (not pruned by CHECKPOINT_TTL_DAYS). Phase 3.
"""

from __future__ import annotations


def get_checkpointer() -> object:
    raise NotImplementedError("Phase 3: langgraph-checkpoint-postgres wiring")
