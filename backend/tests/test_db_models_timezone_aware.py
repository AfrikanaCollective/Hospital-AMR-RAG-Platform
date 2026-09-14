"""Every `datetime` column in the schema must be timezone-aware (DEVIATIONS.md
#56).

A plain `Mapped[datetime] = mapped_column()` compiles to Postgres
`TIMESTAMP WITHOUT TIME ZONE`, which silently drops tzinfo on every
write/read round-trip. This was found by actually writing an `AuditEvent` to
a real Postgres and reading it back — a real DB, not SQLite (whose JSONB
incompatibility already keeps it out of this offline suite) or a mocked
session, was needed to surface it, since the mismatch only appears after a
genuine round-trip. Asserted here structurally, offline, so it can't recur
silently in a new column.
"""

from __future__ import annotations

from sqlalchemy import DateTime

# Import every schema module so its tables register on Base.metadata,
# regardless of what else pytest has collected.
import app.db.models.audit  # noqa: F401
import app.db.models.corpus  # noqa: F401
import app.db.models.eval  # noqa: F401
import app.db.models.hitl  # noqa: F401
import app.db.models.iam  # noqa: F401
import app.db.models.memory  # noqa: F401
import app.db.models.records  # noqa: F401
from app.db.base import Base


def test_every_datetime_column_is_timezone_aware() -> None:
    offending = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime) and not column.type.timezone
    ]
    assert offending == [], f"timezone-naive datetime column(s): {offending}"
