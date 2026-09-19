"""Deterministic, LLM-free narrative construction for ablation-study
questions (DEVIATIONS.md #156, operator instruction).

`app.eval.question_gen.generate.generate_question` (the production
narrative generator, used by `app.eval.tasks`/`app.eval.auto_seed` for the
harness fixed-testset and the clinician review queue) stays exactly as-is —
this module is a separate, additional path, not a replacement. It exists
because the ablation study needs exact, reproducible control over what a
question says (in particular, an explicit list of assessed-and-**absent**
findings, not just present ones) that an LLM paraphrase step would make
harder to guarantee.

Built entirely from a record's own field *values* — nothing here can
fabricate a clinical fact, so there is no LLM call and no no-fabrication
validator step (there is nothing for one to catch). The same tri-state
discipline used throughout this codebase (ARCH-039) applies: an
`examination_findings`/`maternal_risk_factors` member only ever appears
here if it was actually assessed (`present` is `True` or `False`); a member
never assessed for is never mentioned at all — never a fabricated negative.

**Medications and interventions are never included**, same as the
production generator (DEVIATIONS.md #155) — this module reuses none of
`generate.py`'s field-subset logic, but the constraint is intentionally
enforced here too, independently, since it is a hard requirement, not an
implementation detail worth coupling the two modules over.
"""

from __future__ import annotations

from app.eval.question_gen.generate import _VITAL_FIELDS


def _join_natural(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _humanize(name: str) -> str:
    return name.replace("_", " ")


def _tri_state_lists(members: list[dict]) -> tuple[list[str], list[str]]:
    """`(present_names, absent_names)` from a `{name, present}`-shaped list
    (`examination_findings` / `maternal_risk_factors`) — a member with no
    `present` key at all (shouldn't happen for a real record, since these
    lists only ever contain assessed members per `app.ingestion.eav`) is
    excluded from both, never guessed either way."""
    present = [_humanize(m["name"]) for m in members if m.get("present") is True]
    absent = [_humanize(m["name"]) for m in members if m.get("present") is False]
    return present, absent


def _patient_sentence(record: dict) -> str:
    encounter = record.get("encounter") or {}
    parts = [f"The newborn patient is {record.get('sex') or 'of unspecified sex'}"]
    if (day_of_life := encounter.get("day_of_life")) is not None:
        parts.append(f"is {day_of_life} days old")
    if (ga := encounter.get("gestational_age_weeks")) is not None:
        parts.append(f"born at {ga} weeks gestation")
    if (bw := encounter.get("birth_weight_g")) is not None:
        parts.append(f"with a birth weight of {bw} g")
    if care_setting := encounter.get("care_setting"):
        parts.append(f"currently in {care_setting}")
    if presenting := encounter.get("presenting_complaint"):
        parts.append(f"presenting with {presenting}")
    return ", ".join(parts) + "."


def _maternal_risk_factors_line(record: dict) -> str | None:
    present, absent = _tri_state_lists(record.get("maternal_risk_factors") or [])
    if not (present or absent):
        return None
    clauses = []
    if present:
        clauses.append(f"the mother had {_join_natural(present)}")
    if absent:
        clauses.append(f"the mother did NOT have {_join_natural(absent)}")
    return "Maternal risk factors assessed: " + "; ".join(clauses) + "."


def _vitals_line(record: dict) -> str | None:
    vitals_list = record.get("vitals") or []
    if not vitals_list:
        return None
    v = vitals_list[0]
    parts = [f"{label} {v[key]}" for key, label in _VITAL_FIELDS if v.get(key) is not None]
    return "Vitals at admission: " + ", ".join(parts) + "." if parts else None


def _examination_findings_lines(record: dict) -> list[str]:
    present, absent = _tri_state_lists(record.get("examination_findings") or [])
    if not (present or absent):
        return []
    lines = ["From assessments at admission:"]
    if present:
        lines.append(f"- the patient had {_join_natural(present)}.")
    if absent:
        lines.append(f"- the patient did NOT have {_join_natural(absent)}.")
    return lines


def build_deterministic_narrative(record: dict, *, topic: str) -> str:
    """Build one ablation-study question narrative from `record` (a
    `PatientRecord`-shaped dict) and an explicit `topic` (the caller's
    responsibility to supply — ARCH §15.1 step 2's automatic topic-matching
    is not implemented, DEVIATIONS.md #67/#156)."""
    lines: list[str] = [
        f"What does the guideline recommend about {topic} based only on "
        "the content provided below:",
        "",
        _patient_sentence(record),
    ]
    if maternal_line := _maternal_risk_factors_line(record):
        lines.append(maternal_line)
    if vitals_line := _vitals_line(record):
        lines.append(vitals_line)
    lines.extend(_examination_findings_lines(record))
    return "\n".join(lines)
