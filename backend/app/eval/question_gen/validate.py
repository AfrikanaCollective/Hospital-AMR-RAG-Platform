"""No-fabrication validator for generated narratives (ARCH §15.1 step 5; PRD-061).

Every clinical entity mentioned in a generated question (symptoms, findings,
history, timeline, demographics, meds) must map to a field VALUE actually
present in the source record. Any unmapped entity => reject and regenerate
(up to QGEN_MAX_RETRIES). The validator report is stored in
`generator_meta.validator_report`.

**Approach (DEVIATIONS.md #66):** word-overlap against the record's own
values, not a medical NER/entity-linking model — no such model is in scope
here, and "determinism where it matters" (CLAUDE.md §4) favours a checkable,
testable rule over an opaque one. This is a conservative approximation, not a
true clinical entity linker: it can be fooled by a paraphrase that uses none
of the record's actual words, and it can't tell a genuinely fabricated
finding from an unusual word choice — logged as a known limitation, not
silently assumed to be exact. Every significant word in the generated text
must be explained by either (a) the record's own field *values* (never field
names — PRD-080's "no values" rule is for `field_index`, not this — this
validator intentionally DOES read the plaintext record to check the
narrative against it, since the narrative itself is about to be shown to a
clinician regardless) or (b) a small fixed set of guideline-lookup framing
words ("what", "does", "the", "guideline", "recommend", ...) that describe
the question's *shape*, not the patient, or (c) the target guideline's own
topic vocabulary, when supplied — mentioning the topic being asked about is
not a fabricated patient fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.retrieval.sparse import analyze

# Question-shape scaffolding — not patient facts, always allowed. Deliberately
# small and literal (not "safe words in general") so it stays auditable.
_FRAMING_WORDS = frozenset(
    {
        "what",
        "does",
        "do",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "had",
        "the",
        "a",
        "an",
        "for",
        "with",
        "in",
        "of",
        "and",
        "or",
        "at",
        "on",
        "to",
        "this",
        "that",
        "presenting",
        "presents",
        "present",
        "presented",
        "infant",
        "infants",
        "newborn",
        "newborns",
        "neonate",
        "neonatal",
        "patient",
        "baby",
        "admission",
        "admitted",
        "age",
        "aged",
        "day",
        "days",
        "old",
        "who",
        "given",
        "when",
        "guideline",
        "guidelines",
        "recommend",
        "recommends",
        "recommended",
        "recommendation",
        "say",
        "says",
        "state",
        "states",
        "management",
        "diagnosis",
        "assessment",
        "assessing",
        "regarding",
        "about",
        "male",
        "female",
        # Category/connective words for describing what's listed, not a
        # patient fact in themselves (DEVIATIONS.md #115 — found live: a
        # real gateway model naturally uses these when rendering the
        # record's own section labels — e.g. "current medications", "an
        # examination finding of..." — into a sentence; rejecting them
        # rejected every real vitals/intervention-bearing record almost
        # regardless of content). None of these can introduce a new
        # clinical fact on their own — the specific value/name attached to
        # them must still independently be in `record_vocab`.
        "currently",
        "receiving",
        "including",
        "such",
        "showing",
        "care",
        "setting",
        "current",
        "life",
        "addresses",
        "presentation",
        "question",
        "steps",
        "strategies",
        "guideline-lookup",
        "examination",
        "findings",
        "interventions",
        "medications",
        # Generic descriptive adjectives/verbs — carry no clinical fact of
        # their own, found recurring live across otherwise-clean narratives
        # after the additions above (DEVIATIONS.md #115).
        "appropriate",
        "undergoing",
        "considerations",
        "exhibiting",
    }
)

# Units of measurement AND the vitals-label words needed to describe a
# measurement in English, not clinical facts in their own right — a numeric
# field's value (e.g. heart_rate_bpm=140.0) is already in the record
# vocabulary; the narrative must still be able to say "a heart rate of 140
# bpm" rather than just the bare number "140". This set used to read "no
# 'breathing'/'heart'/'oxygen' here... those must still trace to an actual
# record value, so a fabricated finding stays catchable" — that conflated a
# measurement LABEL (safe: the number it's attached to still has to match
# the record) with an actual clinical FINDING word (unsafe: e.g.
# "grunting"/"cyanosis" name a fact in their own right and must still come
# from the record's own `problems`/`examination_findings` values, which
# this set does not touch). Found live against a real gateway model
# (DEVIATIONS.md #115): every real vitals-bearing record failed validation
# on words like "heart"/"rate"/"temperature" — there is no way to describe
# an admission-vitals reading in English without them, so this wasn't a
# model-compliance gap, it was an incompleteness in what this set allowed.
_UNIT_WORDS = frozenset(
    {
        "weeks",
        "week",
        "gestation",
        "gestational",
        "grams",
        "gram",
        "kg",
        "kilograms",
        "celsius",
        "degrees",
        "percent",
        "bpm",
        "mmhg",
        "minute",
        "minutes",
        "hour",
        "hours",
        "second",
        "seconds",
        "heart",
        "rate",
        "respiratory",
        "temperature",
        "spo2",
        "capillary",
        "refill",
        "weight",
        "vitals",
        "vital",
        "signs",
        "birth",
    }
)

# Identity/meta fields never contribute clinical vocabulary (and shouldn't be
# mentioned in a narrative anyway).
_EXCLUDED_VALUE_FIELDS = frozenset(
    {"record_id", "mrn", "given_name", "family_name", "dataset_provenance", "schema_version"}
)


@dataclass
class ValidatorReport:
    ok: bool
    mapped_entities: list[str] = field(default_factory=list)
    unmapped_entities: list[str] = field(default_factory=list)
    notes: str | None = None


def _flatten_values(value: Any, out: list[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _flatten_values(v, out)
    elif isinstance(value, list):
        for item in value:
            _flatten_values(item, out)
    elif isinstance(value, bool) or value is None:
        return  # a flag or an absent field carries no narrative-checkable text
    else:
        out.append(str(value))


def record_value_vocabulary(source_record: dict) -> set[str]:
    """Every significant word appearing in one of the record's own field
    *values* (never field names) — the grounding vocabulary a generated
    narrative's clinical claims must stay within."""
    strings: list[str] = []
    for k, v in source_record.items():
        if k in _EXCLUDED_VALUE_FIELDS:
            continue
        _flatten_values(v, strings)
    vocab: set[str] = set()
    for s in strings:
        vocab.update(analyze(s))
    return vocab


def validate_narrative(
    question_text: str, source_record: dict, *, allowed_topic_terms: list[str] | None = None
) -> ValidatorReport:
    record_vocab = record_value_vocabulary(source_record)
    topic_vocab: set[str] = set()
    for term in allowed_topic_terms or []:
        topic_vocab.update(analyze(term))
    allowed = record_vocab | _FRAMING_WORDS | _UNIT_WORDS | topic_vocab

    tokens = analyze(question_text)
    seen = sorted(set(tokens))
    mapped = [t for t in seen if t in record_vocab]
    unmapped = [t for t in seen if t not in allowed]

    notes = None
    if unmapped:
        notes = (
            f"{len(unmapped)} word(s) in the generated question do not map to the "
            f"source record's own field values or the allowed framing/topic vocabulary: "
            f"{unmapped}"
        )
    return ValidatorReport(
        ok=not unmapped, mapped_entities=mapped, unmapped_entities=unmapped, notes=notes
    )
