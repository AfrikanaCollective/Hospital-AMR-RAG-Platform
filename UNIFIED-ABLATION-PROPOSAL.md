# Unified Hierarchical Ablation — Checkpoint Proposal

Streamlines three currently-separate ablation studies —
`app/eval/model_ablation` (PRD-110/ARCH-041, SapBERT/MedCPT/BM25),
`app/eval/orchestration_ablation` (PRD-111, single-stage/criteria-reuse/
vocabulary), and `app/eval/retrieval_tuning` (PRD-109/ARCH-040, alpha/k
sweep) — into one three-level hierarchical experiment, per operator
request 2026-09-22. Not yet implemented; this document is the checkpoint
artifact CLAUDE.md §2's phase-checkpoint protocol requires before that
work starts ("never chain phases in one pass").

---

## 1. Motivation

The operator asked to reorganize the ablation studies "to be more
streamlined," specifically: collapse the present/absent (Level 1),
vocabulary-enrichment (Level 2), and embedding-strategy (Level 3)
questions — each currently answered by a *different* module, on
*different* corpora/question pools, with *different*, independently
hardcoded `K_VALUES`/`MRR_K` constants — into one nested design evaluated
**per query, per condition**, so the same 16 leaf configurations can be
paired-compared for every patient/query rather than read off three
separate PNGs that were never run against the same pool at the same time.

## 2. Current state, and a real doc-drift gap found while investigating

Before designing anything, per this proposal's own instruction ("inspect
the existing RAG pipeline... reuse existing components"), the three
existing ablation modules and their supporting infrastructure were read in
full. Two things are directly reusable as-is (§3); one real, pre-existing
documentation defect was found and should be fixed in the same change:

**`PRD-109`, `PRD-110`, `PRD-111` and `ARCH-040`, `ARCH-041` do not exist
in `PRD.md`/`ARCHITECTURE.md`.** They are used throughout `DEVIATIONS.md`
and `TRACEABILITY.md` as if real (Phase 6 retrieval tuning, the Phase 2
embedding ablation, and Phase 7's orchestration ablation all cite them
extensively, and real code/tests/reports were built and shipped against
them) — but `PRD.md`'s own highest requirement is `PRD-108`, and
`ARCHITECTURE.md`'s own highest section is `ARCH-042` (§9.4, written) with
040/041 never written at all. This is exactly the kind of staleness
CLAUDE.md §6 calls a defect. **Proposed fix, bundled into this phase**:
backfill `PRD-109/110/111` and `ARCH-040/041` into their canonical
documents (text drawn from what `TRACEABILITY.md`'s own rows already
describe them as, since that's the closest thing to an approved
description on record), then this proposal's own new mechanism takes the
next free IDs: **`PRD-112`** and **`ARCH-043`**.

**What's directly reusable, unchanged** (per the instruction not to
duplicate existing logic):

| Concern | Existing implementation | Reuse as-is? |
|---|---|---|
| BM25 ranking | `model_ablation.ablation._bm25_rank` (`store.single_vector_search(using="sparse", ...)`) | yes |
| SapBERT / MedCPT ranking | `model_ablation.ablation._cosine_rank` + `model_ablation.encoders.get_sapbert_encoder`/`get_medcpt_encoders` (no hardcoded model names, `MODEL_ABLATION_BACKEND=stub\|local`, `SAPBERT_MODEL_ID`/`MEDCPT_*_MODEL_ID` + `*_VERIFIED` flags) | yes |
| RRF combine | `model_ablation.ablation._rrf_combine` | yes |
| Alpha-weighted BM25/dense blend | `retrieval_tuning.offline_fusion.weighted_rank`/`fetch_candidate_scores` | yes, generalized per §3.3/§4 point 1 |
| Vocabulary/concept enrichment | `orchestration_ablation.augment.build_arm_c_query` → `app.records.concepts.evaluate_concepts` | yes |
| Present/assessed-absent tri-state rendering | `question_gen.deterministic._tri_state_lists`/`build_deterministic_narrative` | yes for L1-B; **L1-A (present-only rendering) does not exist yet — new, small, additive function**, see §4 |
| `mrr`/`precision_recall_at_k` | `app.eval.metrics` | yes, unchanged |
| Percentile bootstrap CI | `model_ablation.ablation._bootstrap_ci` (private, one module only) | promote to shared, add a **paired** variant (§4 point 3) — does not exist anywhere today |
| Source-record resolution (de-identified + synthetic) | `orchestration_ablation.augment.resolve_source_record`/`load_synthetic_record_index`, `auto_seed._existing_accepted_records`-style de-identified lookup | yes |

**What does NOT change** (production behavior, per the instruction "do not
change the current default RAG behaviour"): `app.retrieval.hybrid.retrieve()`
(the real `/query` path — server-side Qdrant RRF, no alpha knob, single
production embedding) is untouched. This is a new, additive,
independently-executable offline module, exactly like its three
predecessors.

## 3. Proposed design

### 3.1 Level 1 — clinical-sign query construction

- **L1-A (present-only)**: a new function,
  `question_gen.deterministic.build_present_only_narrative(record, *,
  topic)` — same structure as `build_deterministic_narrative`, but
  `_examination_findings_lines`/`_maternal_risk_factors_line` render only
  the `present is True` branch, entirely omitting the "did NOT have"
  clause. No inference: a sign that was never assessed is still never
  mentioned (unchanged from today).
- **L1-B (all assessed)**: `build_deterministic_narrative`, unchanged —
  already exactly this.

### 3.2 Level 2 — vocabulary/concept enrichment

- **L2-enriched**: `orchestration_ablation.augment.build_arm_c_query(text,
  vocabulary, record)`, reused unchanged, applied to whichever L1 text was
  built.
- **L2-raw**: the L1 text itself, no augmentation.
- **Flagged, not a defect to fix in this phase**: `evaluate_concepts` only
  ever fires `_PRESENCE_OPERATOR` concepts when a feature is `True`
  (`app/records/concepts.py`) — assessed-absent and never-assessed are
  handled identically (never fire). Reusing it unchanged, as instructed,
  means the *enrichment terms themselves* will be identical whether L1-A or
  L1-B produced the base text — only the base text's own present/absent
  wording differs. This is a direct, structural consequence of reuse, not
  a new bug; the comparability requirement in §III ("change only the
  presence/absence of derived vocabulary") still holds *within* each L1
  branch, it's just that L1 itself doesn't currently change what the
  enrichment step can see.

### 3.3 Level 3 — retrieval/embedding configuration

**Decided (operator, 2026-09-22): alpha is generalized into Level 3.**
`L3-BM25` has no dense channel, so it is not alpha-swept (one ranking).
Each of the other three arms becomes a *family* of rankings across
`ALPHA_VALUES` (§3.6), reusing `offline_fusion.weighted_rank`'s
min-max-normalize-then-blend formula (`alpha*bm25_norm +
(1-alpha)*dense_norm`) — but that formula's existing *candidate-fetching*
half (`fetch_candidate_scores`) is Qdrant-ANN-specific (built for the one
production embedding, server-side search) and can't be reused for
SapBERT/MedCPT, which `model_ablation` deliberately never writes to Qdrant
and instead ranks brute-force over the in-memory corpus. A new
`unified_ablation.blend.brute_force_candidate_scores(bm25_rank,
dense_cosine_scores)` — analogous to `fetch_candidate_scores`'s output
shape, but sourced from `_bm25_rank`/`_cosine_rank`'s own already-computed
rankings/similarities instead of a second Qdrant round-trip — is genuinely
new, small integration code, not a duplicate of anything existing:

- **L3-BM25**: `_bm25_rank` alone. No alpha.
- **L3-BM25+SapBERT**: `weighted_rank`-style blend of BM25 vs. SapBERT
  cosine scores, swept over `ALPHA_VALUES`.
- **L3-BM25+MedCPT**: same, vs. MedCPT cosine scores.
- **L3-BM25+SapBERT+MedCPT**: same, vs. a combined dense score. **Judgment
  call, flagged for DEVIATIONS once implementation starts**: the combined
  dense score is the mean of SapBERT's and MedCPT's own already
  min-max-normalized cosine scores (simple, symmetric, no new parameter) —
  not a second RRF layer inside the alpha blend, which would mix two
  different combination mechanisms (rank-based RRF and score-based alpha)
  in one arm. Will flag this plainly rather than silently pick it if it
  turns out to matter once real numbers are in.

This means Level 3 now has its own internal (arm × alpha) grid, on top of
the K sweep (§3.6) — the full per-arm sweep is `4 arms × up to 6 alphas ×
10 k-values` (BM25 alone only ever contributes 10 rows, not 60, since it
has no alpha dimension).

### 3.4 Explicit configuration representation (requirement V)

A single frozen dataclass, not scattered conditionals:

```python
@dataclass(frozen=True)
class AblationArm:
    level1: Literal["present_only", "all_assessed"]
    level2: Literal["enriched", "raw"]
    level3: Literal["bm25", "bm25_sapbert", "bm25_medcpt", "bm25_sapbert_medcpt"]

ALL_ARMS: tuple[AblationArm, ...] = tuple(
    AblationArm(l1, l2, l3)
    for l1 in get_args(AblationArm.__annotations__["level1"])
    for l2 in get_args(AblationArm.__annotations__["level2"])
    for l3 in get_args(AblationArm.__annotations__["level3"])
)  # 16, generated, never hand-enumerated
```

### 3.5 Per-query result record (requirement IX)

One frozen dataclass row per (query, arm, k) — `query_id`,
`patient_id_or_case_id`, `experiment_id`, `level1_condition`,
`level2_condition`, `level3_condition`, `k`, `alpha`, `query_text`,
`concept_enriched_query`, `retrieved_ids`, `relevant_ids`,
`first_relevant_rank`, `reciprocal_rank_at_k` — exactly the fields listed,
one JSON object per line in `per_query_results.jsonl` (§4 point 2) before
any aggregation, so paired comparisons across all 16 conditions for the
same query are always reconstructable. **`alpha` is always a real float,
never `null`**: for the three dense-bearing Level-3 arms it's the actual
swept value (§3.3); for `L3-BM25` (no dense channel to blend) it's fixed
at `1.0` — the mathematically consistent degenerate case per
`weighted_rank`'s own existing convention (`alpha=1` → pure BM25,
`alpha=0` → pure dense) — so every row stays directly comparable/filterable
on `alpha` with no special-cased `None` downstream. One row per (query,
arm, k, alpha) — restated precisely: for `L3-BM25` this is 1 alpha value ×
`len(K_VALUES)` rows; for the three dense-bearing arms it's
`len(ALPHA_VALUES)` × `len(K_VALUES)` rows each.

### 3.6 Metric: MRR@K, K and alpha not hardcoded

New shared `app/eval/ablation_config.py` (or added fields to
`app.config.Settings`, per requirement's "use existing configuration
conventions" — these three constants are currently duplicated,
independently, in `model_ablation.ablation`, `retrieval_tuning.sweep`, and
`orchestration_ablation.ablation`, each with its own value and its own
follow-up-request history — DEVIATIONS #177/#178/#179/#180-#183):

```python
K_VALUES: tuple[int, ...] = tuple(range(2, 21, 2))   # 2..20 step 2 (requirement VI)
ALPHA_VALUES: tuple[float, ...] = tuple(round(i / 10, 1) for i in range(0, 11, 2))  # 0.0..1.0 step 0.2
MRR_K = <settings-driven, default matching the now-settled retrieval_tuning value, 12>
```

exposed via `settings.ablation_k_values`/`settings.ablation_alpha_values`
env-overridable strings (same parse-a-comma-list convention
`qgen_composition` already uses), so every one of the three existing
modules *and* the new unified one read from one place. The three existing
modules keep their own current values until/unless a future change
migrates them — not silently changed by this phase (requirement XIII:
"do not change the current default... behaviour").

### 3.7 Statistics (requirement XII)

New `app/eval/bootstrap.py`:
- `bootstrap_ci(scores, *, rng)` — promoted, unchanged math, from
  `model_ablation.ablation._bootstrap_ci`.
- `paired_bootstrap_ci_delta(scores_a, scores_b, *, rng)` — resamples the
  **same query indices** each draw for both arms (not two independent
  resamples), returns the CI on `mean(scores_a) - mean(scores_b)`. Does
  not exist anywhere in the codebase today.

Three comparisons, each via the paired delta:
1. **Level 1**: present-only vs. all-assessed, pooling over L2×L3×k (or
   sliced per L2×L3×alpha×k — §4 point 4).
2. **Level 2, within each L1**: enriched vs. raw.
3. **Level 3, within each L1×L2**: pairwise among the four arms (6 pairs)
   or each vs. BM25 as the reference (3 pairs, chosen — §4 point 5).

### 3.8 Reproducibility (requirement X)

Every run persists a config snapshot alongside results: `experiment_id`
(uuid), `k_values`, `alpha_values`, `mrr_k`, `sapbert_model_id` +
`sapbert_model_verified`, `medcpt_*_model_id` + `*_verified`,
`rrf_k`/`candidate_depth`, `template_version` (`"deterministic-v1"` /
`"deterministic-present-only-v1"`), `dataset_id` + record-pool size,
`timestamp`, `seed` — same fields `eval.Result.config_snapshot` already
captures for a single run, generalized to the whole experiment.

### 3.9 CLI (requirement XI)

`python -m scripts.run_unified_ablation [--out-dir DIR] [--concepts-path
PATH] [--k-values ...] [--alpha-values ...]`, matching
`run_model_ablation.py`/`run_orchestration_ablation.py`'s exact existing
argparse/env-var/Makefile conventions (`make unified-ablation-report`, the
same `pip install -q -e ".[retrieval-tuning,local-models]"` pattern).

## 4. Design decisions

**Resolved by the operator (2026-09-22):**

1. **Alpha is generalized into Level 3** (§3.3) — not kept as
   `retrieval_tuning`'s separate, existing tool. Real new integration work,
   not just wiring together existing pieces; accepted.
2. **Per-query results are file-based**, under a run-scoped directory, not
   a new Postgres table:
   ```
   results/
   └── ablation/
       └── <run_id>/
           ├── configuration.json       # §3.8 reproducibility snapshot
           └── per_query_results.jsonl  # one line per (query, arm, k) — §3.5 fields
   ```
   `<run_id>` — a timestamp-based or uuid-based identifier, generated per
   run, matching `configuration.json`'s own recorded `timestamp`/
   `experiment_id`. Chosen over `app/eval/unified_ablation/reports/` (the
   other three modules' PNG-only convention) since this run also has a
   *lot* of per-query rows to keep (16 arms × alphas × k per query) that a
   PNG report never needs to retain — a dedicated `results/` tree at repo
   root keeps that bulk out of `app/`. Reports (PNGs/summary tables) still
   render from `per_query_results.jsonl`, written alongside it in the same
   run directory.

**Defaulted, not yet confirmed — flagged here rather than silently
decided, easy to redirect before implementation starts:**

3. **Bootstrap resample count/seed for the new paired variant**: reusing
   `model_ablation`'s existing `_BOOTSTRAP_N=10_000`/`_BOOTSTRAP_SEED=1234`
   for consistency with everything already shipped.
4. **Level 1 comparison population**: one pooled paired-delta summary over
   every L2×L3×alpha×k combination, plus the full per-slice breakdown kept
   in `per_query_results.jsonl` for anyone who wants to slice it further —
   not 16+ separate headline numbers.
5. **Level 3 comparisons**: each of the 3 dense-bearing arms (at each
   alpha) vs. plain `BM25` as the single reference, matching how
   `model_ablation` already treats `rrf_production` as *its* reference —
   not all pairwise combinations. Full pairwise deltas stay reconstructable
   from the raw per-query data regardless.
6. **Combining SapBERT+MedCPT before the alpha blend** (§3.3): mean of
   their two already-normalized cosine scores, not a nested RRF-inside-alpha
   step.

## 5. Deliverables

- `PRD.md`: backfill `PRD-109/110/111` (§2), add `PRD-112` (this phase).
- `ARCHITECTURE.md`: backfill `ARCH-040/041` (§2), add `ARCH-043`.
- `app/eval/question_gen/deterministic.py`: add
  `build_present_only_narrative` (additive).
- `app/eval/ablation_config.py` (new): `AblationArm`, `ALL_ARMS`,
  `K_VALUES`/`ALPHA_VALUES`/`MRR_K` settings-driven.
- `app/eval/bootstrap.py` (new): `bootstrap_ci`, `paired_bootstrap_ci_delta`
  — `model_ablation.ablation` migrated to import from here instead of its
  own private copy (behavior-identical, confirmed by its existing tests
  still passing unchanged).
- `app/eval/unified_ablation/` (new package): `runner.py` (the 16-arm ×
  k × alpha sweep, wired from existing rankers per §3.3), `report.py`
  (Level-1/2/3 summary charts, dataviz-skill-validated palette matching
  the other three reports), `per_query.py` (the persistence layer per
  §4 point 2's storage layout).
- `scripts/run_unified_ablation.py` (new CLI).
- `Makefile`: `unified-ablation-report` target.
- Tests: unit tests for `AblationArm`/`ALL_ARMS` generation,
  `build_present_only_narrative`, `bootstrap_ci`/`paired_bootstrap_ci_delta`
  (including a regression test that paired CIs are narrower than naive
  independent-sample CIs on correlated data — the whole point of pairing);
  offline integration test for the runner against a `:memory:` Qdrant +
  stub encoders, same fixture pattern as `test_model_ablation.py`.

## 6. Experiment design and metrics

16 leaf arms × `len(K_VALUES)` × (Level-3 dense arms only ×
`len(ALPHA_VALUES)`, per §4 point 1) per query, over the current
`well_supported` calibration pool (100 questions as of DEVIATIONS #191).
Primary outcome: MRR@K per arm, 95% bootstrap CI. Secondary: recall@k per
arm (reusing `precision_recall_at_k`, unchanged), for parity with the
three existing reports' own recall panels.

## 7. Compliance with CLAUDE.md §3

- Rule 1 (PHI): unchanged — same de-identified/synthetic record resolution
  already audited in DEVIATIONS #186-#189.
- Rule 2 (no independent clinical advice): unchanged — this module never
  produces or stores an answer a clinician sees; it scores retrieval
  ranking only, same as its three predecessors.
- Rule 3 (grounding): not applicable — offline ranking evaluation, no
  answer synthesis path touched.
- Rule 4 (CDS boundary): not applicable — no next-step recommendation or
  local-adaptation logic anywhere in this design.
- Rule 5 (no hardcoded models): `SAPBERT_MODEL_ID`/`MEDCPT_*_MODEL_ID` +
  `*_VERIFIED` flags reused unchanged from `model_ablation.encoders`.
- Rule 6 (audit append-only): not applicable — no `audit.audit_event` row
  ever written by any of the three existing ablation modules either.
- Rule 7 (PHI never leaves deployment): unchanged.

## 8. Out of scope for this phase

- Changing `app.retrieval.hybrid.retrieve()` (production `/query` path).
- Extending `evaluate_concepts` to fire on assessed-absent signs (flagged
  §3.2 as a direct consequence of reuse, explicitly deferred per operator
  instruction in DEVIATIONS #191).
- Migrating `retrieval_tuning`/`orchestration_ablation`'s own existing
  reports off their current, independent K/alpha constants — they keep
  running exactly as today until/unless a separate follow-up retires them
  in favor of the unified tool.
- A four-way (not BM25-vs-rest) alpha blend for `BM25+SapBERT+MedCPT` (a
  single BM25-weight parameter against a combined dense score, §4 point 6
  — not three independently-weighted channels).

## 9. Testing plan

Offline only, no network, matching `test_model_ablation.py`/
`test_orchestration_ablation.py`'s established fixture pattern
(`qdrant-client` `:memory:` mode, `EMBEDDING_BACKEND=stub`,
`MODEL_ABLATION_BACKEND=stub`). New: `test_ablation_config.py`,
`test_bootstrap.py`, `test_question_gen_deterministic.py` additions for
`build_present_only_narrative`, `test_unified_ablation.py` for the runner
and per-query record shape. Existing three modules' full test suites must
stay green, unchanged (requirement XIII: "ensure existing tests continue
to pass").

## 10. Docs updated in the same change (once approved and implemented)

`PRD.md`, `ARCHITECTURE.md`, `ARCHITECTURE-ESSENTIALS.md`,
`TRACEABILITY.md` (new `PRD-112`/`ARCH-043` rows, backfilled
`PRD-109/110/111`/`ARCH-040/041` rows), `README.md` (§Status + a dated
narrative entry matching the other three ablations' own entries),
`DEVIATIONS.md` (every judgment call from §4 once resolved, logged at the
moment implementation starts — not retroactively).
