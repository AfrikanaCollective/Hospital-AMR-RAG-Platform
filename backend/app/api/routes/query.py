"""Query endpoint (SCOPE-1.1, SCOPE-2.1, SCOPE-2.2; PRD-011..PRD-016, PRD-105, PRD-107).

POST /query
  Body: QueryRequest (question, optional conversation_id, optional patient_id,
        purpose-of-use via header).
  Flow: orchestrator scope-classifies -> retrieval -> [patient-record
        -> stage-classifier / missing-info] -> synthesis -> citation-verifier
        grounding gate -> assemble + disclaimer OR escalate
        (app.agents.graph.build_graph). Runs inline; returns the full
        QueryResponse (PRD-NFR-1: ~15s p50 soft target on a typical question
        — synchronous is the primary, expected path).
  Never returns an ungrounded answer (PRD-NFR-2). SCOPE-2.3/2.4 intent ->
  escalation with trigger_code=scope_boundary (never answered).

POST /query/async, GET /query/jobs/{job_id} (DEVIATIONS.md #94)
  The Celery-backed counterpart (PRD-105 "async... long-running agent runs")
  for a caller that doesn't want to hold an HTTP connection open for a run
  that may exceed the soft target (a slow SCOPE-2 chain, a gateway fallback
  retry, a deliberate batch/replay tool) — additive, not a replacement: the
  synchronous route's contract and every existing test are unchanged.
  `POST /query/async` does the identical `prepare_query` step (persist the
  user's turn, write the `query` audit event) synchronously, then hands the
  graph run + response persistence to `app.agents.tasks.run_query` and
  returns a job handle immediately; `GET /query/jobs/{job_id}` polls it.

The compiled graph is a process-lifetime singleton per process
(`app.agents.graph_runtime`, shared by this route and the Celery task),
built lazily on first real invocation — never at import time, so importing
this module in tests never opens a real Postgres connection for the
checkpointer. `_GRAPH_INVOKE_FN` is the indirection point tests monkeypatch
to bypass the real graph (and therefore real DB/Qdrant/LLM) entirely.

**Deliberately does NOT use `Depends(get_db)`** (DEVIATIONS.md #95) — that
would hold one request-scoped transaction open across the *entire* graph
invocation, which itself opens several other, separate sessions (each agent
node — `retrieval_agent`, `patient_record_agent`, ... — opens its own via
`app.db.session.session_scope`). A real docker-compose run hit exactly this:
`prepare_query`'s `query` audit-event write took `app.audit.log`'s
serializing advisory lock (DEVIATIONS.md #95) on the outer, still-open
request transaction; `retrieval_agent`'s own `retrieval` audit-event write,
on its own separate connection, then blocked waiting for that same lock —
which the outer transaction could not release until the request finished,
which could not happen until retrieval (the thing waiting) returned. Using
`_SESSION_SCOPE()` explicitly, twice — once for `prepare_query`, committing
and closing before the graph runs; once for `assemble_and_persist_response`,
opened only after the graph returns — means no transaction this route holds
ever overlaps the graph invocation at all.

`Principal.user_id` -> UUID: see `app.api.deps.principal_uuid` (DEVIATIONS.md #75).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.graph_runtime import invoke_graph, new_turn_thread_id
from app.agents.query_pipeline import ROLE, assemble_and_persist_response, prepare_query
from app.agents.tasks import run_query
from app.api.deps import Principal, principal_uuid, purpose_of_use, require_role
from app.db.session import session_scope
from app.schemas.query import QueryJobAccepted, QueryJobStatus, QueryRequest, QueryResponse
from app.worker import celery_app

router = APIRouter()

_GRAPH_INVOKE_FN = invoke_graph
_ASYNC_RESULT_FN = celery_app.AsyncResult
_SESSION_SCOPE = session_scope


def _build_initial_state(
    body: QueryRequest, principal: Principal, purpose: str, conversation_id: uuid.UUID
) -> dict:
    return {
        "conversation_id": str(conversation_id),
        "user_id": str(principal_uuid(principal)),
        "roles": list(principal.roles),
        "purpose": purpose,
        "patient_id": body.patient_id,
        "query": body.question,
        "hospital_constraint": body.hospital_constraint,
    }


@router.post("", response_model=QueryResponse)
async def submit_query(
    body: QueryRequest,
    principal: Principal = Depends(require_role(ROLE)),
    purpose: str = Depends(purpose_of_use),
) -> QueryResponse:
    user_id = principal_uuid(principal)
    with _SESSION_SCOPE() as session:
        conversation_id = prepare_query(
            session,
            question=body.question,
            conversation_id=body.conversation_id,
            patient_id=body.patient_id,
            user_id=user_id,
            purpose=purpose,
        )
    initial_state = _build_initial_state(body, principal, purpose, conversation_id)
    try:
        out = _GRAPH_INVOKE_FN(initial_state, new_turn_thread_id(str(conversation_id)))
    except Exception as exc:  # noqa: BLE001 - never surface an internal error as a clinical answer
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The query pipeline failed unexpectedly."
        ) from exc

    with _SESSION_SCOPE() as session:
        return assemble_and_persist_response(
            session, out, conversation_id=conversation_id, user_id=user_id, purpose=purpose
        )


@router.post("/async", response_model=QueryJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def submit_query_async(
    body: QueryRequest,
    principal: Principal = Depends(require_role(ROLE)),
    purpose: str = Depends(purpose_of_use),
) -> QueryJobAccepted:
    user_id = principal_uuid(principal)
    with _SESSION_SCOPE() as session:
        conversation_id = prepare_query(
            session,
            question=body.question,
            conversation_id=body.conversation_id,
            patient_id=body.patient_id,
            user_id=user_id,
            purpose=purpose,
        )
    initial_state = _build_initial_state(body, principal, purpose, conversation_id)
    async_result = run_query.delay(initial_state)
    return QueryJobAccepted(job_id=async_result.id, conversation_id=str(conversation_id))


@router.get("/jobs/{job_id}", response_model=QueryJobStatus)
async def get_query_job(
    job_id: str,
    _principal: Principal = Depends(require_role(ROLE)),
) -> QueryJobStatus:
    result = _ASYNC_RESULT_FN(job_id)
    if not result.ready():
        return QueryJobStatus(job_id=job_id, status="pending")
    if result.failed():
        return QueryJobStatus(job_id=job_id, status="failed", error=str(result.result))
    return QueryJobStatus(job_id=job_id, status="done", result=QueryResponse(**result.result))
