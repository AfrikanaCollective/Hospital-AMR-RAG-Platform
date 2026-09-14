"""`records.record_field_policy` resolution (ARCH-034; PRD-084, DEVIATIONS.md #87)."""

from __future__ import annotations

from app.auth import rbac


class _FakeSession:
    """`resolve_field_effects` issues one `(field_path, effect)` select scoped
    to `(role, purpose)`; the fake ignores the actual WHERE-clause values
    (matching this suite's established pattern, e.g. `test_auth_repository.py`)
    and just returns the canned rows for whatever policy a test wants to model."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows

    def execute(self, stmt: object) -> object:
        class _Res:
            def __init__(self, rows: list[tuple[str, str]]) -> None:
                self._rows = rows

            def all(self) -> list[tuple[str, str]]:
                return self._rows

        return _Res(self._rows)


def test_exact_match_wins_over_wildcard() -> None:
    session = _FakeSession([("vitals.heart_rate_bpm", "deny"), ("*", "allow")])
    effect = rbac.resolve_field_effect(
        session, "clinician", "clinical_care", "vitals.heart_rate_bpm"
    )
    assert effect == "deny"


def test_wildcard_applies_when_no_exact_row() -> None:
    session = _FakeSession([("*", "allow")])
    effect = rbac.resolve_field_effect(session, "clinician", "clinical_care", "labs.CRP")
    assert effect == "allow"


def test_defaults_to_deny_with_no_matching_policy() -> None:
    session = _FakeSession([])
    effect = rbac.resolve_field_effect(
        session, "reviewer", "clinical_care", "vitals.heart_rate_bpm"
    )
    assert effect == "deny"


def test_bulk_resolves_multiple_fields_in_one_query() -> None:
    session = _FakeSession([("vitals.heart_rate_bpm", "mask"), ("*", "allow")])
    effects = rbac.resolve_field_effects(
        session, "clinician", "clinical_care", ["vitals.heart_rate_bpm", "labs.CRP", "sex"]
    )
    assert effects == {
        "vitals.heart_rate_bpm": "mask",
        "labs.CRP": "allow",
        "sex": "allow",
    }


def test_empty_field_paths_returns_empty_without_querying() -> None:
    def _boom(stmt: object) -> object:  # noqa: ARG001
        raise AssertionError("should not query for an empty field_paths batch")

    session = _FakeSession([])
    session.execute = _boom  # type: ignore[method-assign]
    assert rbac.resolve_field_effects(session, "clinician", "clinical_care", []) == {}


def test_field_allowed_helper() -> None:
    assert rbac.field_allowed("allow") is True
    assert rbac.field_allowed("deny") is False
    assert rbac.field_allowed("mask") is False
