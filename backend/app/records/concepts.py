"""Operator-authored clinical-concept vocabulary: loader, attestation gate,
evaluator (SCOPE-2.6 / ARCH-042; PRD-057).

**Bounded, proposed capability** (DEVIATIONS.md #143/#144/#146/#148). This
module's only current caller is the Phase 7 orchestration ablation
(`app.eval.orchestration_ablation`, PHASE7-PROPOSAL.md) — it is not wired
into any live agent, route, or answer path. A concept label built here is an
**internal retrieval-signal only**: it can be appended to a search query, but
it is never a value in `field_index` and never appears in or supports answer
text (only a retrieved chunk's own quote can support an answer segment,
CLAUDE.md §3 rule 3).

**A threshold is a clinical judgment call — never invented here.** Every
concept's `field`/`operator`/`value`/`source` (and, if present, `synonyms`)
must come from an operator-attested file (`data/clinical_concepts.yaml`,
templated with `TODO_CONFIRM` placeholders). `load_vocabulary` fails closed:
any entry still carrying a placeholder raises `ConceptVocabularyNotAttested`
rather than being silently used, the same pattern
`app.ingestion.records.guard_batch` uses for `DATASET.md`'s attestation gate.
"""

from __future__ import annotations

import operator as _operator_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_PLACEHOLDER = "TODO_CONFIRM"

# Threshold operators: `field` compared against a single numeric `value`.
_THRESHOLD_OPERATORS: dict[str, Any] = {
    ">": _operator_module.gt,
    "<": _operator_module.lt,
    ">=": _operator_module.ge,
    "<=": _operator_module.le,
    "=": _operator_module.eq,
}
# Range: `low <= field <= high` (inclusive both ends), e.g. an age band like
# "7 to 59 days" -- distinct from a single threshold, needs two bounds.
_RANGE_OPERATOR = "between"
# Boolean presence: fires when `field`'s value is exactly `True` (an assessed,
# positive `examination_findings`/`maternal_risk_factors` sign, e.g.
# "apnoea") -- never on a merely-truthy non-bool value, and never on an
# absent/never-assessed field (handled the same way as every other operator,
# via the `field not in features` check in `evaluate_concepts`).
_PRESENCE_OPERATOR = "present"
_ALL_OPERATORS = frozenset({*_THRESHOLD_OPERATORS, _RANGE_OPERATOR, _PRESENCE_OPERATOR})


class ConceptVocabularyNotAttested(Exception):
    """A concept (or the file header) still carries a placeholder value.

    Never caught-and-coerced into a guess — a coding session must not be the
    one deciding a clinical threshold (or a synonym, or a source citation)."""


@dataclass(frozen=True)
class Concept:
    name: str
    field: str
    operator: str
    source: str
    value: float | None = None  # threshold operators only
    low: float | None = None  # `between` only
    high: float | None = None  # `between` only
    synonyms: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(frozen=True)
class ConceptVocabulary:
    authored_by: str
    authored_date: str
    concepts: tuple[Concept, ...] = field(default_factory=tuple)


def _require_attested(value: Any, *, what: str) -> Any:
    if value is None or value == _PLACEHOLDER:
        raise ConceptVocabularyNotAttested(f"{what} is missing or still a placeholder")
    return value


def load_vocabulary(path: str | Path) -> ConceptVocabulary:
    """Parse + attestation-gate a `data/clinical_concepts.yaml`-shaped file.

    `synonyms` is optional (a concept need not have any), but if present it
    must contain no placeholder entries — curated the same way as every
    other operator-supplied field, never auto-generated or inferred. Which
    of `value` (threshold operators), `low`/`high` (`between`), or nothing
    (`present`) is required depends on `operator` — see the module docstring."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    authored_by = _require_attested(raw.get("authored_by"), what="authored_by")
    authored_date = _require_attested(raw.get("authored_date"), what="authored_date")

    concepts: list[Concept] = []
    for name, raw_spec in (raw.get("concepts") or {}).items():
        spec = raw_spec or {}
        op = _require_attested(spec.get("operator"), what=f"concept {name!r} operator")
        if op not in _ALL_OPERATORS:
            raise ConceptVocabularyNotAttested(
                f"concept {name!r} has an unrecognized operator {op!r}"
            )
        field_path = _require_attested(spec.get("field"), what=f"concept {name!r} field")
        source = _require_attested(spec.get("source"), what=f"concept {name!r} source")
        synonyms = tuple(spec.get("synonyms") or ())
        if _PLACEHOLDER in synonyms:
            raise ConceptVocabularyNotAttested(f"concept {name!r} synonyms still has a placeholder")

        value = low = high = None
        if op == _PRESENCE_OPERATOR:
            if any(spec.get(k) is not None for k in ("value", "low", "high")):
                raise ConceptVocabularyNotAttested(
                    f"concept {name!r} uses operator 'present' and must not set value/low/high"
                )
        elif op == _RANGE_OPERATOR:
            low = float(_require_attested(spec.get("low"), what=f"concept {name!r} low"))
            high = float(_require_attested(spec.get("high"), what=f"concept {name!r} high"))
            if low > high:
                raise ConceptVocabularyNotAttested(
                    f"concept {name!r} has low > high ({low} > {high})"
                )
        else:
            value = float(_require_attested(spec.get("value"), what=f"concept {name!r} value"))

        concepts.append(
            Concept(
                name=name,
                field=field_path,
                operator=op,
                source=source,
                value=value,
                low=low,
                high=high,
                synonyms=synonyms,
                notes=spec.get("notes"),
            )
        )
    return ConceptVocabulary(
        authored_by=authored_by, authored_date=authored_date, concepts=tuple(concepts)
    )


def evaluate_concepts(vocabulary: ConceptVocabulary, features: dict[str, Any]) -> list[Concept]:
    """Which concepts match `features` (an `app.records.access.extract_features`
    -shaped dict)? A concept whose `field` is absent from `features` (never
    assessed / not recorded, ARCH-039's tri-state) never fires — same
    discipline as `app.records.criteria.evaluate_criteria`."""
    matched: list[Concept] = []
    for concept in vocabulary.concepts:
        if concept.field not in features:
            continue
        value = features[concept.field]
        if concept.operator == _PRESENCE_OPERATOR:
            if value is True:
                matched.append(concept)
            continue
        if not isinstance(value, int | float):
            continue
        if concept.operator == _RANGE_OPERATOR:
            assert (
                concept.low is not None and concept.high is not None
            )  # guaranteed by load_vocabulary
            if concept.low <= value <= concept.high:
                matched.append(concept)
        elif _THRESHOLD_OPERATORS[concept.operator](value, concept.value):
            matched.append(concept)
    return matched


def build_expansion_term(concept: Concept) -> str:
    """Same technique as `app.retrieval.hybrid._expand_abbreviations`: the
    primary term is preserved as-is (exact/BM25 matches still work), and
    curated synonyms are appended parenthetically so the dense retriever
    (and BM25) has vocabulary for whichever wording a guideline text uses.
    Never invents a synonym beyond the operator-curated list."""
    if not concept.synonyms:
        return concept.name
    return f"{concept.name} ({', '.join(concept.synonyms)})"
