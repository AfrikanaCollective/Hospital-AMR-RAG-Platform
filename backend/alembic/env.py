"""Alembic environment (ARCH-008).

Uses the app settings for the DB URL and `Base.metadata` (with every model
module imported) as the autogenerate target. Schemas + roles are created by
deploy/postgres/init/01_schemas_roles.sql before migrations run.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401  -- registers every table on Base.metadata

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# Only manage objects in our schemas.
_MANAGED_SCHEMAS = {"corpus", "records", "memory", "hitl", "eval", "audit", "iam"}


def _include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ARG001
    schema = getattr(obj, "schema", None)
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
