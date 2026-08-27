"""Import every model module so Base.metadata is complete (Alembic autogenerate).

Schemas (ARCH-008): corpus, records, memory, hitl, eval, audit, iam.
"""

from app.db.models import (  # noqa: F401
    audit,
    corpus,
    eval,
    hitl,
    iam,
    memory,
    records,
)

__all__ = ["audit", "corpus", "eval", "hitl", "iam", "memory", "records"]
