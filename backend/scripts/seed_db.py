"""Seed reference data (ARCH §14.1, ARCH-011).

- rubric domains (the 11, from app.rubric.domains) -> eval.rubric_domain,
- roles (clinician, reviewer, admin, service) -> iam.role,
- a few demo users (dev only): one clinician, three reviewers (clinicians), one admin.

Idempotent. Phase 2 wires the actual DB writes; Phase 1 prints what it would do
so the command exists and is documented.
"""

from __future__ import annotations

from app.db.models.iam import ROLES
from app.rubric.domains import RUBRIC_DOMAINS

DEMO_USERS = [
    ("clinician@example.dev", "Demo Clinician", {"clinician"}, True),
    ("reviewer1@example.dev", "Demo Reviewer One", {"clinician", "reviewer"}, True),
    ("reviewer2@example.dev", "Demo Reviewer Two", {"clinician", "reviewer"}, True),
    ("reviewer3@example.dev", "Demo Reviewer Three", {"clinician", "reviewer"}, True),
    ("admin@example.dev", "Demo Admin", {"admin"}, False),
]


def main() -> int:
    print("[seed] roles:", ", ".join(ROLES))
    print(f"[seed] rubric domains ({len(RUBRIC_DOMAINS)}):",
          ", ".join(d.code for d in RUBRIC_DOMAINS))
    print("[seed] demo users:")
    for email, name, roles, is_clin in DEMO_USERS:
        print(f"       {email:<24} {name:<22} roles={sorted(roles)} clinician={is_clin}")
    print("[seed] DB writes are wired in Phase 2 (alembic + repositories).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
