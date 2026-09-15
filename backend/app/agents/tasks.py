"""Celery task for an async `/query` pipeline run (ARCH-007, PRD-105; DEVIATIONS.md #94).

`run_query` is the async counterpart to `app.api.routes.query`'s synchronous
path, sharing the exact same `app.agents.query_pipeline.assemble_and_persist_response`
logic (and the same `app.agents.graph_runtime.invoke_graph`) so a query
answered via Celery is persisted/audited identically to one answered inline.

The submitting route (`POST /query/async`) still runs
`app.agents.query_pipeline.prepare_query` **synchronously**, before
enqueueing — the user's turn and the `query` audit event record the attempt
immediately, not only once/if the async run completes; this task picks up
from `initial_state` (which already carries the resolved `conversation_id`)
and only has to persist the *response* side.

**Not idempotency-safe on task retry** (ARCH §21c self-critique item 5,
already flagged there, not newly discovered here): `task_acks_late`/
`task_reject_on_worker_lost` (`app.worker`) mean a worker crash mid-task
re-queues it, and a retry would call `append_message`/`write_event` a second
time for the same logical answer. No idempotency key exists yet for this
task family (`process_document` has the same property, guarded only at the
*submission* layer via `content_sha256` — this task has no equivalent
submission-layer guard). Out of scope for this change; flagged, not solved.
"""

from __future__ import annotations

import uuid

from app.agents.graph_runtime import invoke_graph, new_turn_thread_id
from app.agents.query_pipeline import assemble_and_persist_response
from app.db.session import session_scope
from app.worker import celery_app

_INVOKE_GRAPH_FN = invoke_graph


@celery_app.task(name="agents.run_query")
def run_query(initial_state: dict) -> dict:
    conversation_id = initial_state["conversation_id"]
    out = _INVOKE_GRAPH_FN(initial_state, new_turn_thread_id(conversation_id))
    with session_scope() as session:
        response = assemble_and_persist_response(
            session,
            out,
            conversation_id=uuid.UUID(conversation_id),
            user_id=uuid.UUID(initial_state["user_id"]),
            purpose=initial_state["purpose"],
        )
    return response.model_dump(mode="json")
