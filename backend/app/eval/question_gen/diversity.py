"""Diversity filter (ARCH §15.1 step 7; DEVIATIONS.md #67, #113, #187, #188).

Rejects a newly generated narrative whose SOURCE RECORD's clinical content
is too similar to one already accepted in the same generation run (or a
prior one — the comparison pool is every auto-generated question ever
accepted, not just this run's). `QGEN_DEDUP_THRESHOLD`
(`app.config.Settings.qgen_dedup_threshold`) existed as a config knob since
Phase 1 but nothing read it until DEVIATIONS #113 — step 7 was documented
and left unimplemented (DEVIATIONS.md #67, "needs a populated corpus to
check against"). This is plain, deterministic code, not a model call
(CLAUDE.md §4 "determinism where it matters") — no embedding call, no model
call, of any kind.

**Structured-field comparison, not text embeddings (DEVIATIONS.md #188)**:
two earlier embedding-based attempts both failed in practice, live-verified
each time, not assumed:
1. Embedding the generated narrative's own whole-sentence text. Every
   narrative shares one fixed sentence template ("What does the guideline
   recommend for a <sex> infant at <N> weeks gestational age with a birth
   weight of <N> g on day of life <N> in the NBU who has <findings>...?"),
   which swamps a whole-sentence embedding's similarity signal — two records
   with materially different findings (one SpO2 93%, the other SpO2 70%, a
   severe-hypoxia difference) embedded at 0.9544 cosine similarity, above
   even the already-once-raised 0.96 threshold (DEVIATIONS #119), a
   false-positive rejection.
2. Embedding only the clinical-findings fields as free text (a
   `dedup_signature` string), stripping the shared demographic prefix. This
   fixed that ONE case (0.9161, correctly below threshold) but made the
   aggregate picture worse — a random 40-item sample of the accepted pool
   went from 2.3% to 45.6% of pairs at or above 0.92, and a live re-run
   still produced 0/41 new successes. This dataset's clinical vocabulary is
   closed/repetitive enough (~10 recurring NBU exam findings, similar
   vitals ranges) that a general-purpose sentence embedding doesn't reliably
   discriminate it at any threshold, regardless of exact phrasing — and,
   more fundamentally, "similarity to ANY of N growing embeddings" only
   gets more likely to false-positive as N grows, for any fixed threshold
   below 1.0 (exactly DEVIATIONS #119's original symptom recurring, at a
   larger N, despite that entry's own fix).

This module now compares the SOURCE RECORDS' own structured fields
directly: Jaccard similarity over the set of present examination
findings/problems, AND every shared vitals field within a fixed absolute
tolerance — both conditions must hold to reject (either alone isn't enough
evidence of a true near-duplicate; see `is_clinically_near_duplicate`).
"""

from __future__ import annotations

# Absolute tolerance per vitals field, in that field's own units — an
# engineering judgment call for "close enough to not add diversity to the
# review queue", NOT a clinical decision threshold. Contrast
# `data/clinical_concepts.yaml`, which IS operator-attested clinical
# judgment (CLAUDE.md §3 rule 5 territory) — these values never appear in,
# or influence, any answer a clinician sees; they only decide whether two
# GENERATED REVIEW-QUEUE SCENARIOS are too alike to both be worth queuing.
_VITAL_TOLERANCE: dict[str, float] = {
    "heart_rate_bpm": 15.0,
    "resp_rate_bpm": 10.0,
    "temperature_c": 0.5,
    "spo2_percent": 5.0,
    "capillary_refill_seconds": 1.0,
    "weight_g": 200.0,
}


def _findings_set(record: dict) -> frozenset[str]:
    findings = {f["name"] for f in (record.get("examination_findings") or []) if f.get("present")}
    problems = set(record.get("problems") or [])
    return frozenset(findings | problems)


def _vitals_dict(record: dict) -> dict[str, float]:
    vitals_list = record.get("vitals") or []
    if not vitals_list:
        return {}
    v = vitals_list[0]
    return {k: v[k] for k in _VITAL_TOLERANCE if v.get(k) is not None}


def jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """1.0 when both sets are empty — vacuously "identical", no real signal
    either way; matches the "nothing to compare" convention
    `vitals_within_tolerance` also uses for its own empty-overlap case."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def vitals_within_tolerance(a: dict[str, float], b: dict[str, float]) -> bool:
    """True if every vitals field present in BOTH `a` and `b` is within its
    `_VITAL_TOLERANCE` band. A field missing from either side is simply not
    compared — absence isn't evidence of similarity OR difference here, and
    two records sharing no vitals field at all vacuously pass (`True`,
    nothing contradicts a match)."""
    shared_keys = set(a) & set(b)
    if not shared_keys:
        return True
    return all(abs(a[k] - b[k]) <= _VITAL_TOLERANCE[k] for k in shared_keys)


def is_clinically_near_duplicate(
    candidate_record: dict,
    accepted_records: list[dict],
    *,
    findings_jaccard_threshold: float,
) -> bool:
    """True if `candidate_record`'s clinical content is too similar to any
    of `accepted_records`'s — categorical (Jaccard on the present
    examination-findings/problems set) AND numeric (every shared vitals
    field within tolerance) must BOTH hold for a given accepted record to
    count as a match; neither signal alone is treated as sufficient
    evidence of a true near-duplicate (DEVIATIONS.md #188).

    A candidate with NO structured clinical content at all (no findings, no
    problems, no vitals) is never flagged — there is no real signal to
    compare, and treating it as a match would vacuously reject it against
    every other equally-empty record for no clinical reason."""
    cand_findings = _findings_set(candidate_record)
    cand_vitals = _vitals_dict(candidate_record)
    if not cand_findings and not cand_vitals:
        return False
    for accepted in accepted_records:
        acc_findings = _findings_set(accepted)
        acc_vitals = _vitals_dict(accepted)
        if jaccard_similarity(
            cand_findings, acc_findings
        ) >= findings_jaccard_threshold and vitals_within_tolerance(cand_vitals, acc_vitals):
            return True
    return False
