# Phase 7 Checkpoint Proposal — Single-Stage vs. Two Multi-Step Orchestration Variants (Criteria-Grounded and Operator-Vocabulary Query Augmentation)

**Status:** Proposed — awaiting Checkpoint 7 approval. Nothing in this
document has been implemented. Phases 0–6 are complete and
checkpoint-approved (see README.md §Status); this proposes new, additive
work, per the phase-checkpoint protocol in CLAUDE.md §2.

**Note on the name "Phase 7":** `PHASE6-PROPOSAL.md` §7 provisionally
earmarked "Phase 7" for a *different* proposal — "Production Fusion-Weight
Adoption" — conditional on Phase 6's sweep showing a fixed `alpha` that
robustly beat the RRF baseline. It didn't (DEVIATIONS.md #123: "no alpha
robustly beats the RRF baseline... Phase 7 is not triggered"), so that
proposal was never written and the name is unclaimed. This document uses it
for the orchestration ablation instead, which is unrelated to fusion weights.

**Proposed requirement ID:** `PRD-111` (next free slot after `PRD-110`,
following the same "evidence-gathering ablation, no production change"
precedent as `PRD-109` [Phase 6] and `PRD-110`
[`PHASE2-EMBEDDING-ABLATION-PROPOSAL.md`] — confirm against
`PRD.md`/`TRACEABILITY.md` before assigning, in case other work has landed
IDs in the meantime).

**Relationship to `PRD-057`/`SCOPE-2.6`/`ARCH-042` (DEVIATIONS.md
#143/#144/#146) — updated from this document's first draft:** this phase
**does** now build a bounded version of that mechanism, for arm C only (§2).
It is deliberately narrower than what full `SCOPE-2.6` approval would cover:
the concept vocabulary is used **only** to augment an offline retrieval
query in this eval harness — never wired into `app/agents/graph.py`, never
seen by any live agent, never able to reach answer text. Approving this
proposal is not the same as approving `SCOPE-2.6` for production use; that
remains a separate, later, its-own-checkpoint decision (§7).

---

## 1. Motivation

The operator asked, while reviewing the ingestion pipeline: could
patient-record content be pre-processed into a more retrieval-useful form
before the embedding/LLM call, and would that measurably help? This phase
answers that empirically, the same way Phase 6 answered "does a weighted
fusion beat RRF" and the embedding-ablation proposal answered "does a
biomedical encoder beat the general-purpose one" — with a reproducible
offline comparison against the existing gold-chunk eval-question set, not a
production change.

Discussion while scoping this phase surfaced two structurally different ways
to do that pre-processing (§2), with different coverage and different
governance requirements, so both are compared side by side rather than
picking one.

## 2. Three arms

**Arm A — single-stage (baseline).** The auto-generated hypothetical
question (`app/eval/question_gen/generate.py`, scope-1 framed per
PRD-060/061 — the patient's clinical details are already written into the
question's prose, e.g. "...a 2-day-old neonate presenting with grunting and
a respiratory rate of 65...") goes straight to `retrieve()` as-is. One
retrieval call. This is exactly what Phase 6 and the embedding ablation
already measured as their baseline arm.

**Arm B — criteria-reuse (multi-step, grounded).** Two retrieval calls, and
it only ever repeats a fact a guideline *already states*:
1. Retrieve once with the raw question (identical to Arm A).
2. From those results, take items where `chunk_type == "criteria"` (mirrors
   `missing_info_agent.run`) and run
   `evaluate_criteria(criteria, extract_features(source_record))` against
   the question's own underlying synthetic record (`source_record_id` — the
   same join Phase 6/the embedding ablation use for gold-chunk lookup).
3. Collect `matched=True` criteria's `field`/`operator`/`value` text (e.g.
   `"respiratory rate > 60"`) as short expansion clauses.
4. Retrieve again with `question_text + "; " + matched_clauses` if any
   matched; otherwise Arm B == Arm A for that question (§3).

A "concept" here is a matched criterion from a chunk already retrieved for
this same question — always traceable to a citation, needs no new capability
or vocabulary, no new governance. This is what the first draft of this
document proposed alone.

**Arm C — operator-vocabulary (multi-step, curated).** One retrieval call,
using an operator-authored concept vocabulary (`data/clinical_concepts.yaml`,
ARCH-042 §9.4) computed **before** retrieval, independent of what any
guideline document says:
1. Load `data/clinical_concepts.yaml`; for each concept whose `field` is
   present in `extract_features(source_record)` (never a `None`/absent
   value), evaluate `operator`/`value` against the recorded value.
2. For each matched concept, build an expansion term from its name plus its
   operator-curated `synonyms` (spelling variants and phrase-level
   equivalents alike, e.g. `"tachypnoea (tachypnea, fast breathing, rapid
   breathing)"`) — same technique as `app.retrieval.hybrid._expand_
   abbreviations`: the primary term is preserved as-is for exact/BM25
   matching, and the parenthetical adds vocabulary for whichever wording the
   guideline text happens to use, without inventing content beyond the
   curated list (§4).
3. Retrieve once with `question_text + "; " + "; ".join(expansion_terms)`.

Unlike Arm B, Arm C doesn't need a first pass to already have found the
right guideline — it can help find it in the first place. The cost: a
concept's threshold isn't tied to a citation, so (per ARCH-042 §9.4) it can
only ever influence which chunks get retrieved, never appear in or support
answer text. **This arm requires `data/clinical_concepts.yaml` to actually
be authored and attested by the operator before it can run for real** — see
§4's blocking note.

## 3. Judgment calls to log once this phase starts

- **Arm B's "concept" = matched retrieved criterion, not an independent
  vocabulary** — the main interpretive call this proposal's first draft
  made, unchanged.
- **Eval-set filter**: primary metric uses the same filter as Phase 6
  (`expected_outcome == well_supported`, non-empty `gold_relevant_chunks`)
  for comparability across all three arms. `missing_info_expected` questions
  (sparse records by design) are run as a **secondary, exploratory** slice —
  no guaranteed gold chunk, reported separately rather than pooled.
- **No matched criteria/concepts → that arm == Arm A** for that question,
  not skipped. The fraction of questions where this happens is reported per
  arm (§5) — for Arm B, a high fraction means the corpus rarely gives
  augmentation anything to reuse; for Arm C, a high fraction means the
  operator's vocabulary rarely applies to this record population. Both are
  real findings, not harness bugs.
- **Arm C's vocabulary schema and attestation gate** (§4) — decided this
  session (mirrors `DATASET.md`'s attestation pattern); to be confirmed by
  the operator, who also owns filling in real thresholds *and* synonyms,
  before the real (non-toy) Arm C report can be produced.
- **Synonyms are operator-curated, in the same attested file, not
  auto-normalized** (confirmed by the operator when this was raised):
  spelling variants (e.g. "tachypnoea"/"tachypnea") and phrase-level
  equivalents (e.g. "fast breathing") both go in one `synonyms:` list per
  concept — one audit trail, one attestation gate, rather than splitting
  "assistant-decided spelling rules" from "operator-decided synonyms" across
  two mechanisms.

## 4. `data/clinical_concepts.yaml` — proposed schema, and why it's a blocking gate, not a stub

```yaml
# Operator-authored clinical-concept vocabulary (SCOPE-2.6 / ARCH-042 §9.4).
# Every entry needs a non-empty `source` (a named guideline, clinical
# reference, or institutional protocol) -- entries are internal
# retrieval-signal labels ONLY, never quoted or referenced as guideline
# content in any answer (CLAUDE.md §3 rule 3). A concept with a placeholder
# or missing `value`/`source` is rejected by the loader, not silently used
# (same fail-closed pattern as DATASET.md's attestation gate). `synonyms`
# (spelling variants and phrase-level equivalents alike -- both are the
# operator's call, not this session's) are optional but curated the same
# way: never auto-generated, never inferred.
authored_by: "TODO_CONFIRM"
authored_date: "TODO_CONFIRM"
concepts:
  tachypnoea:
    field: vitals.resp_rate_bpm
    operator: ">"
    value: TODO_CONFIRM   # no real clinical threshold decided yet
    source: "TODO_CONFIRM"
    synonyms: ["TODO_CONFIRM"]   # e.g. spelling variants, "fast breathing" --
                                 # operator's call; used for query augmentation
                                 # only (§2), same as an abbreviation expansion
    notes: "TODO_CONFIRM (e.g. age/gestational-age dependence, if any)"
```

This file ships as a **template with placeholder values**, the same way
`DATASET.md` ships with `TODO_CONFIRM` fields the operator must fill before
`make ingest-deid` runs. The loader (`app/records/concepts.py`) raises a
`ConceptVocabularyNotAttested`-style error (mirroring
`app.ingestion.records.MissingAttestationError`) for any entry still
carrying a placeholder, and Arm C's *real* eval report cannot be produced
until the operator authors real content — this is a hard blocking
dependency, not a nice-to-have, and this session will not invent clinical
thresholds to work around it. `tests/test_orchestration_ablation.py` (§8)
exercises the loader/evaluator mechanics against a clearly non-clinical
fixture vocabulary (e.g. a threshold of `999999` with `source: "unit-test
fixture, not a real clinical value"`), never against invented real-looking
thresholds.

**Update (2026-09-19, after real authoring — DEVIATIONS.md #153):** the
single-threshold shape above wasn't enough for what the operator actually
needed to express. Extended to three operator shapes, same attestation
discipline throughout: `>`/`</>=/<=`/`=` (threshold, against `value`,
unchanged); `between` (inclusive `low`/`high` — e.g. an age band like "7 to
59 days"); `present` (boolean — fires only when an `examination_findings`/
`maternal_risk_factors` field is exactly `True`, for signs like apnoea that
are already booleans in the record, never a numeric threshold). Also found,
in the operator's own first real draft of this file: most `field` references
used plausible-but-wrong names (`demographics.age_days`,
`vitals.heart_rate`, `vitals.temparature`, ...) that don't match
`extract_features`'s real output (`encounter.day_of_life`,
`vitals.heart_rate_bpm`, `vitals.temperature_c`, ...) — they'd have loaded
without error and simply never fired. Corrected the field-path strings and
formalized three range-typo'd entries (`operator: "<", value: 3` copy-pasted
across three concepts describing three different day ranges in their own
`notes`) into `between` — both are mechanical fixes following what the
operator's own thresholds/notes already stated, not new clinical decisions.
**Still not extended**: string/categorical field comparison (`sex`,
`care_setting`) — referencing one loads fine but never fires; not built
since it wasn't asked for.

## 5. Deliverables

```
backend/app/records/concepts.py                      # ARCH-042 mechanism:
                                                       # loader + attestation
                                                       # gate + evaluator
data/clinical_concepts.yaml                           # operator-authored
                                                       # template (TODO_CONFIRM)
backend/app/eval/orchestration_ablation/
  __init__.py
  augment.py    # Arm B (criteria-reuse) and Arm C (vocabulary) query builders
  ablation.py   # runs all three arms over the eval-question pool via the
                # existing app.retrieval.hybrid.retrieve; scores via
                # app.eval.metrics (reused, not reimplemented)
  report.py     # chart generation, dataviz-skill palette
backend/scripts/run_orchestration_ablation.py         # CLI entry point
backend/tests/test_concepts.py                        # concepts.py loader:
                                                       # attestation gate,
                                                       # never-fires-on-None
backend/tests/test_orchestration_ablation.py          # offline, :memory:
                                                       # Qdrant, stub backend,
                                                       # fixture vocabulary
backend/app/eval/orchestration_ablation/reports/*.png
```

## 6. Experiment design and metrics

- **Primary**: recall@k (`k` ∈ {5, 8, 24}, matching the eval harness's
  existing reporting set) and MRR@8, across all three arms, on the
  `well_supported` filter (§3). Reuses `app.eval.metrics.precision_recall_at_k`
  / `mrr` unchanged, same as Phase 6.
- **Secondary/exploratory**: the same two metrics on the `missing_info_expected`
  slice, reported separately, per arm.
- **Per-arm "did augmentation fire" rate** (§3): fraction of questions where
  Arm B/Arm C actually differed from Arm A, per slice — the denominator
  check without which the recall numbers can't be interpreted.
- **Retrieval-call count per arm**: Arm A = 1, Arm B = 2, Arm C = 1 per
  question — a real operational/latency difference between the two
  multi-step designs, reported alongside accuracy, not just a footnote.
- **Chart 1** — grouped bar/paired-point comparison of recall@k across all
  three arms at each `k` in the reporting set, `well_supported` slice.
- **Chart 2** — same comparison, MRR@8, both slices side by side.
- **Chart 3** — "augmentation fired" rate, one bar per arm (B, C) per slice
  (Arm A has no such rate — it never augments).
- All charts: seaborn, written to
  `backend/app/eval/orchestration_ablation/reports/`; the `dataviz` skill
  loaded before writing per its own trigger condition, palette/format
  consistent with Phase 6/the embedding ablation's reports. A 3-arm
  comparison needs a categorical palette check (3 series is within the
  validated CVD-safe categorical count — no sequential-ramp reasoning needed
  here, unlike Phase 6's ordered `alpha`/`k` dials).

## 7. Compliance with CLAUDE.md §3

- **No PHI**: source records are the existing `synthetic-generator-v1` eval
  question pool only (`source_record_id`); no de-identified data touched. No
  new data source.
- **No hardcoded models**: reuses `retrieve()`, `evaluate_criteria`,
  `extract_features` as-is; no new model reference.
- **No invented clinical facts**: Arm C's thresholds come only from an
  operator-attested file (§4); the loader fails closed on any placeholder.
  This session authors the schema and the gate, never the thresholds
  themselves.
- **Determinism**: `evaluate_criteria`, `map_criterion_field`, the
  vocabulary evaluator, and both arms' clause-construction are all plain
  code — consistent with "grounding/confidence/citation resolution is
  deterministic, not model calls." The only model calls in Arms B/C are the
  same embedding call `retrieve()` already makes, once or twice per question.
- **Grounding preserved for both arms**: Arm B's clauses trace to a citation
  by construction (§2). Arm C's clauses do not, but per ARCH-042 §9.4 that
  is safe *because* query augmentation sits upstream of citation
  verification — whatever chunk ends up in a hypothetical future answer
  still has to independently pass the existing §8.3 grounding/quote check,
  unchanged. Neither arm can cause an answer to cite something unsupported.
- **No production path touched**: `app/agents/graph.py`, `hybrid.py`,
  `missing_info_agent.py`, and every live endpoint are unmodified; no new
  `audit.audit_event` writes. `app/records/concepts.py` is new code but is
  called only from this eval harness, not from any agent or route.
- **CDS boundary**: not implicated for either arm. Both reorder/duplicate an
  existing retrieval call; neither produces a recommendation, and Arm C's
  labels never reach answer text (§7 above).

## 8. Out of scope for Phase 7

**Not included:** any change to the live orchestrator graph, to
`missing_info_agent`/`stage_classifier_agent`, or to what any endpoint
returns; wiring either arm's query augmentation into production even if this
ablation shows a clear improvement — that would be its own future proposal
requiring its own checkpoint, re-running the full gating-test suite
(`test_scope_boundary.py`, `no_guideline_expected` grounding cases,
`disclaimer_present_rate`, `test_audit_append_only.py`) against the changed
retrieval path, and a live-stack verification pass (per the pattern in
DEVIATIONS.md #122, #131 — real infra has caught real bugs offline runs
missed in every prior phase); authoring real values into
`data/clinical_concepts.yaml` (operator's task, §4, not this session's); any
use of concept labels in answer text, missing-info escalation logic, or
stage classification (Arm C's mechanism is retrieval-query augmentation
only, per ARCH-042 §9.4 — extending it further is separately scoped).

## 9. Testing plan

- `backend/tests/test_concepts.py`: unit tests for the loader/evaluator
  against a fixture `clinical_concepts.yaml` — attestation gate rejects
  placeholder entries (including a placeholder `synonyms` list), evaluator
  never fires on a `None`/absent feature, never fires on a field never
  assessed, and the expansion-term builder includes a matched concept's
  `synonyms` in the parenthetical exactly as `_expand_abbreviations` does
  (original term preserved, synonyms appended, nothing invented beyond the
  fixture's own list). Offline, no network.
- `backend/tests/test_orchestration_ablation.py`: a small fixture corpus
  (a handful of chunks including at least one `criteria`-type chunk) plus a
  small fixture patient record and a fixture (non-clinical) vocabulary,
  embedded Qdrant `:memory:`, `EMBEDDING_BACKEND=stub` — same pattern as
  `test_retrieval_tuning.py` / `test_model_ablation.py` — validates all
  three arms' query-building and re-retrieve/score arithmetic, including the
  "no match → falls back to Arm A" case (§3). Runs in `make test` (offline,
  no network, per CLAUDE.md §5).
- The full run over the real eval-question pool (§6) is a manual/CI-optional
  target (e.g. `make orchestration-ablation-report`), not part of the pytest
  gating suite — analysis tooling producing a report, not a shipped safety
  gate, same as Phase 6/the embedding ablation. **Arm C's real-data report
  specifically cannot be produced until `data/clinical_concepts.yaml` is
  attested** (§4) — the harness will report Arm A/B results and skip Arm C
  with an explicit "not attested" message rather than fail the whole run.

## 10. Docs updated in the same change (once approved and implemented)

- `TRACEABILITY.md`: new row for `PRD-111`; `PRD-057`/`SCOPE-2.6`/`ARCH-042`
  rows updated from "not started — proposed only" to reflect the bounded,
  eval-only implementation once it lands.
- `README.md`: Status table gets a Phase 7 row; §Status prose gets a short
  paragraph, matching the style of Phases 1–6; `data/` section gains a
  `clinical_concepts.yaml` entry alongside `record_schema.json`.
- `DEVIATIONS.md`: entries for the eval-set-filter choice (§3), the
  vocabulary schema/attestation design as actually implemented (§4, if it
  differs from this draft), and the real Arm C attestation status once the
  operator provides it.

---

**Checkpoint 7:** Stop here. Do not begin implementation until this proposal
is explicitly approved — including that Arm C's mechanism, though it
implements a bounded slice of `SCOPE-2.6`/`ARCH-042`, does **not** constitute
approval of that capability for production use (see the "Relationship to
PRD-057/SCOPE-2.6/ARCH-042" note above), and that any production wiring of
query augmentation from either arm is a separate, later checkpoint (§8).
