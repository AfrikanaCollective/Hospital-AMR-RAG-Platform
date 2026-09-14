"""LangGraph Postgres checkpointer wiring (ARCH §11; PRD-023).

Long agent runs are checkpointed so they survive worker restarts and can be
inspected/resumed. A checkpoint tied to an open escalation is retained until
the escalation resolves (not pruned by CHECKPOINT_TTL_DAYS — pruning is a
Phase-4 retention job, not implemented here).

`get_checkpointer()` is a process-lifetime singleton: `PostgresSaver` holds a
live psycopg connection, so it is opened once and reused, not per-call.
`app.agents.graph.build_graph()` calls this only when the caller doesn't pass
its own checkpointer — tests inject `langgraph.checkpoint.memory.MemorySaver()`
(a real, in-process, no-DB checkpointer shipped with langgraph itself) instead,
keeping unit tests offline (CLAUDE.md §5) without mocking LangGraph's own API.

Three things a real-Postgres verification run surfaced that no offline test
could (all DEVIATIONS.md #82):

1. `PostgresSaver.from_conn_string` wants a plain psycopg DSN
   (`postgresql://...`); `settings.database_url` is SQLAlchemy-formatted
   (`postgresql+psycopg://...`). `_to_psycopg_dsn` strips the driver
   qualifier.
2. `PostgresSaver.setup()` issues `CREATE TABLE` — DDL the restricted runtime
   `hrag_app` role (`database_url`) does not have, by design (the same
   least-privilege boundary DEVIATIONS.md #61 documents for Alembic). Setup
   runs once, in a short-lived connection using the elevated
   `alembic_database_url`, then is discarded.
3. `PostgresSaver`'s own tables (`checkpoints`, `checkpoint_writes`, ...) are
   unqualified — they land wherever the connection's `search_path` resolves,
   normally `public`, which `hrag_app` has no grants on at all (every grant
   in `01_schemas_roles.sql` is scoped to the platform's named schemas).
   `_with_search_path` points both the setup connection and the long-lived
   operational connection at the `memory` schema — the schema the Phase-1
   schema-bootstrap SQL's own comment already earmarked for "conversations,
   messages, patient_context, checkpoints". Because `memory` already has
   `ALTER DEFAULT PRIVILEGES ... GRANT SELECT, INSERT, UPDATE, DELETE ON
   TABLES TO hrag_app`, tables the elevated setup connection creates there
   are immediately usable by the regular `hrag_app`-authenticated operational
   connection with no further grants needed.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.config import get_settings

_saver_cm: Any = None
_saver: Any = None

_CHECKPOINTER_SCHEMA = "memory"


def _to_psycopg_dsn(sqlalchemy_url: str) -> str:
    scheme, _, rest = sqlalchemy_url.partition("://")
    driver = scheme.split("+", 1)[0]  # postgresql+psycopg -> postgresql
    return f"{driver}://{rest}"


def _with_search_path(dsn: str, schema: str = _CHECKPOINTER_SCHEMA) -> str:
    options = quote(f"-c search_path={schema}")
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}options={options}"


def get_checkpointer() -> Any:
    global _saver_cm, _saver  # noqa: PLW0603 - process-lifetime singleton; see module docstring
    if _saver is None:
        # Deferred: avoids importing psycopg for every caller that never
        # calls this function (most tests inject MemorySaver instead).
        from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415

        settings = get_settings()

        setup_dsn = _with_search_path(_to_psycopg_dsn(settings.alembic_database_url))
        with PostgresSaver.from_conn_string(setup_dsn) as setup_saver:
            setup_saver.setup()

        operational_dsn = _with_search_path(_to_psycopg_dsn(settings.database_url))
        _saver_cm = PostgresSaver.from_conn_string(operational_dsn)
        _saver = _saver_cm.__enter__()
    return _saver


def close_checkpointer() -> None:
    global _saver_cm, _saver  # noqa: PLW0603 - process-lifetime singleton; see module docstring
    if _saver_cm is not None:
        _saver_cm.__exit__(None, None, None)
    _saver_cm = None
    _saver = None
