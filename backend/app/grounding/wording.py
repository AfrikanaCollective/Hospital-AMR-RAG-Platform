"""Deterministic wording / scope filter (ARCH §8.3 step 4, ARCH-037; SCOPE-1.2, PRD-088).

Second line of defense behind the prompt templates. Blocks:
- second-person imperatives / "you should" / "recommend that you",
- dosing or therapy specifics not present in a cited quote,
- text that reads as a next-step plan for a specific patient.
A trip => safety_filter escalation. Safe to extend the marker lists.

Phase 3 wires this into the verifier; the marker lists here are usable now and
are covered by tests.
"""

from __future__ import annotations

import re

DIRECTIVE_PATTERNS: tuple[str, ...] = (
    r"\byou should\b",
    r"\byou must\b",
    r"\bwe recommend (that )?you\b",
    r"\bi recommend\b",
    r"\bstart (the patient on|them on)\b",
    r"\badminister\b .*\bto (this|the) patient\b",
    r"\bthe next step (for (this|the) patient )?is\b",
    r"\bmy advice\b",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in DIRECTIVE_PATTERNS]


def has_directive_phrasing(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED)


def scan_segment(text: str, *, cited_quotes: list[str]) -> list[str]:
    """Return a list of violation reason codes for one segment. Empty => clean."""
    reasons: list[str] = []
    if has_directive_phrasing(text):
        reasons.append("directive_phrasing")
    # dosing/therapy-beyond-source and patient-specific-plan checks: Phase 3.
    return reasons
