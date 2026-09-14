"""Alembic environment (ARCH-008).

Uses `Base.metadata` (with every model module imported) as the autogenerate
target. Schemas + roles are created by deploy/postgres/init/01_schemas_roles.sql
before migrations run.

Connects with `settings.alembic_database_url` (an elevated, DDL-capable
credential), NOT `settings.database_url` (the restricted runtime `hrag_app`
role, which deliberately has no CREATE privilege — DEVIATIONS.md #61).
"""

from __future__ import annotations

from sqlalchemy import engine_from_config, pool

import app.db.models  # noqa: F401  -- registers every table on Base.metadata
from alembic import context
from app.config import get_settings
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().alembic_database_url)

target_metadata = Base.metadata

# Only manage objects in our schemas.
_MANAGED_SCHEMAS = {"corpus", "records", "memory", "hitl", "eval", "audit", "iam"}
# `langgraph-checkpoint-postgres` manages its own tables via `PostgresSaver.setup()`
# (its own internal migration mechanism, distinct from ours) — this repo's
# `memory.LangGraphCheckpoint` model exists only so the schema module documents
# the seam; Alembic must not create or manage a table for it (DEVIATIONS.md #62).
_UNMANAGED_TABLES = {"memory.langgraph_checkpoint"}


def _include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ARG001
    schema = getattr(obj, "schema", None)
    if type_ == "table" and f"{schema}.{name}" in _UNMANAGED_TABLES:
        return False
    if type_ in {"table", "column"} and schema is not None:
        return schema in _MANAGED_SCHEMAS
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=_include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
