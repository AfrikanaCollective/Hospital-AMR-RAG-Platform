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

---

## 11. Addendum (approved 2026-09-23, Option B — IMPLEMENTED and run live, then SUPERSEDED by §12 the same day): RRF counterparts for every dense-bearing Level-3 arm

Phases 1-10 above are implemented and were run for real 2026-09-22
(DEVIATIONS #192-#197) — see `TRACEABILITY.md`'s `PRD-112`/`ARCH-043` rows
for the real result. This addendum, proposed after the operator asked
whether production's actual fusion mechanism (RRF) could be added to the
same hierarchy the four original Level-3 arms already swept, was approved
(Option B, §11.3) and implemented the same day — `ALL_ARMS` grew from 16
to 28, `summarize_level3_mechanism` added, a 4th report panel added, and
run live against the real 238-question corpus (DEVIATIONS #198). See
§11.8 below for the real result.

### 11.1 Why this wasn't in scope already

The four existing Level-3 arms (`bm25`, `bm25_sapbert`, `bm25_medcpt`,
`bm25_sapbert_medcpt`) all use the **same** fusion mechanism — a linear
alpha-weighted blend (`retrieval_tuning.offline_fusion.weighted_rank`,
reused unchanged, §3.3). That mechanism is *not* what production actually
does: `app.retrieval.hybrid.retrieve()` (ARCH-003) fuses via server-side
Qdrant **RRF** (rank-based, no alpha weight at all), and none of Phase 8's
own arms exercise that algorithm — the closest thing today is
`model_ablation.ablation`'s own separate `rrf_production` reference arm,
outside this hierarchy entirely. So today's Level 3 answers "which
*channels*, alpha-blended, beat plain BM25" but not "does the *actual
production fusion algorithm*, applied to these channels, beat plain BM25
too" — a real gap now that Level 3's alpha-blend arms found a large,
statistically distinguishable SapBERT effect (DEVIATIONS #197): is that
effect specific to linear blending, or does it survive under RRF too?

### 11.2 What's directly reusable, unchanged

| Concern | Existing implementation | Reuse as-is? |
|---|---|---|
| RRF fusion algorithm | `model_ablation.ablation._rrf_combine(rankings, *, rrf_k)` — pure, already offline/brute-force-compatible (no ANN dependency, matches this module's own convention) | yes |
| RRF constant | `app.config.Settings.rrf_k` (default 60) — the **same** constant production's real `hybrid.retrieve()` already uses | yes — makes the new arm a faithful reproduction of production's own fusion constant, not an independently-drifting duplicate |
| Per-channel raw scores | `unified_ablation.blend.bm25_raw_scores`/`cosine_raw_scores` — already computed once per (question, Level 1, Level 2) in `runner.sweep_questions`, reused for the alpha-blend arms today | yes — `_rrf_combine` needs *rankings* (sorted chunk-id lists), so the only new code is sorting an already-computed score dict, not a new retrieval call |

No new retrieval logic, no new model, no new config setting (`rrf_k`
already exists and is already config-driven, never hardcoded).

### 11.3 Design decision: which channels does the RRF arm fuse? — **Option B chosen (operator decision, 2026-09-23)**

Production RRF fuses exactly **two** channels (one sparse + one dense
embedding) — it has no 3-way variant. This hierarchy's dense-bearing arms
are 2- and 3-channel. Three options were laid out; the operator chose
**Option B** over the smaller Option A specifically for its completeness:
every existing alpha-blend arm gets a same-channels RRF twin, so channel
choice and fusion mechanism are both independently testable, not just the
one 3-way RRF vs. 3-way alpha-blend comparison Option A would have given.

**Chosen: three new arms** — `rrf_sapbert`, `rrf_medcpt`,
`rrf_sapbert_medcpt` — one RRF counterpart per existing dense-bearing
alpha-blend arm. Level 3 grows from 4 to 7 configurations; `ALL_ARMS`
grows from 16 to 28 (2×2×7).

**Simplification within Option B (my own call, flagged rather than
silently the more complex path):** the original sketch of Option B
proposed reworking `AblationArm.level3` from one flat `Literal` into two
crossed fields (channel × mechanism). That's unnecessary — `bm25` itself
already sits outside any clean channel×mechanism grid (it has no
"mechanism" choice at all, no dense channel to blend/fuse against), so a
true 2-field cross-product would still need a special case for it, same
as today. Keeping `Level3Condition` a **single flat 7-value `Literal`**
(`"bm25"`, `"bm25_sapbert"`, `"rrf_sapbert"`, `"bm25_medcpt"`,
`"rrf_medcpt"`, `"bm25_sapbert_medcpt"`, `"rrf_sapbert_medcpt"`) extends
the exact pattern `ablation_config.py` already uses today, with zero
dataclass restructuring, and `ALL_ARMS`'s own generator comprehension
(`for l3 in LEVEL3_CONDITIONS`) doesn't change shape at all — just grows
from 4 to 7 members in that one tuple.

`alpha_values_for` now needs "no alpha dimension" to match a *set* rather
than a single string equality check: `{"bm25", "rrf_sapbert",
"rrf_medcpt", "rrf_sapbert_medcpt"}` all get the fixed `BM25_ONLY_ALPHA`
(1.0) sentinel, not a sweep. **Naming judgment call, flagged**: keeping
the existing `BM25_ONLY_ALPHA` constant name (rather than introducing a
second, differently-named sentinel with the identical value and identical
"no alpha dimension" meaning) is a deliberate minimal-diff choice — every
existing call site/test referencing `BM25_ONLY_ALPHA` keeps working
unchanged. Its docstring will be broadened to state it now covers every
arm with no alpha dimension, not only the literal `bm25` arm.

### 11.4 A second question this design surfaces: same-channel mechanism comparison

Option B's whole motivation (§11.1) was "does the alpha-blend arms' own
SapBERT effect survive under RRF too?" — that's a **same-channel,
different-mechanism** question (`rrf_sapbert` vs. `bm25_sapbert`), not
"does this arm beat plain BM25" (the comparison every arm already gets).
Both comparisons are kept, as two separate functions matching the
existing one-function-per-statistical-question convention
(`summarize_level1`/`level2`/`level3`, `app.eval.unified_ablation.summary`):

- `summarize_level3` (existing, extended): every non-`bm25` arm (now 6,
  up from 3) vs. `bm25`, within each Level 1 × Level 2 slice — 6 × 4 = 24
  comparisons, up from 12.
- `summarize_level3_mechanism` (new): for each of the 3 channels
  (`sapbert`, `medcpt`, `sapbert_medcpt`), `rrf_<channel>` vs.
  `bm25_<channel>` — the actual "does RRF preserve/beat the alpha-blend
  effect" question — 3 × 4 = 12 comparisons.

### 11.5 Scope of the change (Option B, as refined above)

- `app/eval/ablation_config.py`: `Level3Condition` grows to 7 values (flat
  `Literal`, no dataclass restructuring); `alpha_values_for` checks
  membership in a `_NO_ALPHA_ARMS` frozenset instead of a single `!=
  "bm25"` comparison.
- `app/eval/unified_ablation/blend.py`: new `rrf_combine_scores(*score_dicts, rrf_k) -> list[str]`
  — sorts each already-computed score dict into a ranking, calls
  `model_ablation.ablation._rrf_combine` unchanged.
- `app/eval/unified_ablation/runner.py`: `_rank_for_arm` gains three
  branches (`rrf_sapbert`, `rrf_medcpt`, `rrf_sapbert_medcpt`);
  `settings.rrf_k` threaded through the same way `k_grid`/`alpha_values`
  already are.
- `app/eval/unified_ablation/summary.py`: `summarize_level3` extended to
  all 6 non-`bm25` arms (24 comparisons); new `summarize_level3_mechanism`
  for the 3 same-channel alpha-vs-RRF comparisons (12 comparisons).
- `app/eval/unified_ablation/report.py`: Panel C gains 3 more series (7
  total colors/markers — past the 6-slot validated categorical order, so
  the palette needs re-checking, likely a shape+color combination like
  `model_ablation.report`'s own stage-marker convention rather than 7
  distinct hues); a new Panel D for the mechanism comparison.
- Tests: `test_ablation_config.py` (28-arm count, all 4 no-alpha arms'
  fixed-alpha behavior), `test_unified_ablation_blend.py`
  (`rrf_combine_scores` matches `_rrf_combine` exactly on a
  hand-constructed case), `test_unified_ablation_runner.py`/
  `test_unified_ablation_summary.py` (grid/row-count assertions updated
  for 28 arms; new tests for `summarize_level3_mechanism`).
- **A second real run** would be needed once implemented — this
  addendum's whole point is new arms, so the existing 2026-09-22 run's
  `per_query_results.jsonl` has no `rrf_*` rows to retroactively mine.
  Row count per question grows from 760 to 880: per (Level 1, Level 2)
  combination, the 7 Level-3 arms contribute `1 (bm25) + 6 (bm25_sapbert)
  + 1 (rrf_sapbert) + 6 (bm25_medcpt) + 1 (rrf_medcpt) + 6
  (bm25_sapbert_medcpt) + 1 (rrf_sapbert_medcpt) = 22` arm-alpha rows
  (4 arms with no alpha dimension — `bm25` and the 3 `rrf_*` arms — each
  contribute 1 row; the 3 alpha-blend dense arms each contribute the full
  6-value sweep), × 10 k values = 220, × 4 (Level 1 × Level 2) = 880 rows
  per question. This will be verified against the real run's own printed
  row count once implemented, not assumed from this arithmetic alone —
  matching this project's own established practice (the original 16-arm
  design's own 760-per-question figure was likewise confirmed against a
  live test/run, not just derived on paper).

### 11.6 Out of scope (unchanged from §8)

Still never touches `app.retrieval.hybrid.retrieve()` itself — this adds
three more *offline* arms alongside the existing four, it does not change
what production RRF does or read `rrf_k` differently than production
already does.

### 11.7 Testing plan

Same offline-only, `:memory:` Qdrant + stub-backend convention as every
other arm in this module (§9) — `_rrf_combine` itself already has its own
existing test coverage in `test_model_ablation.py` and is reused
unchanged, not re-tested from scratch.

### 11.8 Real result (2026-09-23, DEVIATIONS #198)

Run live against the same 238-question/311-chunk corpus as the original
run, real SapBERT/MedCPT, 880 rows/question (209,440 total). Row count
matched §11.5's hand-derivation exactly (`4 x 22 x 10 = 880`), verified
against the real run's own printed count, not assumed.

**The mechanism comparison this addendum was built to answer**
(`summarize_level3_mechanism`, Panel D): **RRF does not merely preserve
the alpha-blend arms' own SapBERT effect — it modestly *amplifies* it.**
`rrf_sapbert` beats its own `bm25_sapbert` sibling in all 4 Level-1 x
Level-2 slices (+0.053 to +0.109 MRR@12, three of four CIs excluding
zero). `rrf_medcpt` vs. `bm25_medcpt` is mixed/near-zero in every slice
(no CI clearly excludes zero either direction). `rrf_sapbert_medcpt` vs.
`bm25_sapbert_medcpt` is mixed — positive and CI-excluding-zero in 2 of 4
slices, indistinguishable from zero in the other 2.

Consistent with this, every `rrf_sapbert` vs. plain-`bm25` delta
(`summarize_level3`, Panel C) is larger than its `bm25_sapbert`
counterpart's own delta (e.g. present_only/raw: alpha-blend +0.132 vs.
RRF +0.209; all_assessed/enriched: alpha-blend +0.119 vs. RRF +0.228) —
RRF fusion is, on this corpus and at this N, the stronger of the two
fusion mechanisms for the SapBERT channel specifically.

**Not acted on**, same posture as every other ablation result this
project has produced: production `app.retrieval.hybrid.retrieve()` is
untouched; a production-reopening decision (e.g. "should production RRF
add a SapBERT channel") is separate, unapproved, later work. Full
reproducibility snapshot and per-query data:
`results/ablation/20260923T042249Z-95df853f/`.

---

## 12. Restructured 2026-09-23 (operator-supplied hierarchy, DEVIATIONS.md
#201) — SUPERSEDES §11 entirely

The operator supplied a complete nested-tree specification for the
hierarchy, redefining Level 3 and the primary metric. This is **not an
extension** of §11's RRF work the way §11 extended §1-10 — it **replaces**
it. MedCPT and RRF support (both the original 3-channel design and the
§11 addendum) were removed from the codebase, not deprecated in place.

### 12.1 The new hierarchy

Level 1 and Level 2 are unchanged (present-only vs. all-assessed clinical
signs; vocabulary-enriched vs. raw query). **Level 3 is a single
continuous BM25/SapBERT weighted-rank-fusion sweep**:

```
w_BM25 ∈ {0.0, 0.2, 0.4, 0.6, 0.8, 1.0}
```

6 points at 0.2 granularity (**revised 2026-09-25, §14** — this section
originally specified 11 points at 0.1 granularity, itself up from the
original 6 at 0.2; the grid is now back to 0.2). `w_BM25 =
0.0` is pure SapBERT, `w_BM25 = 1.0` is pure BM25 — the same
`retrieval_tuning.offline_fusion.weighted_rank` formula every prior
design already used, just no longer branched by named "arm identity."
MedCPT (both the standalone `bm25_medcpt`/`bm25_sapbert_medcpt` arms and
their §11 RRF counterparts) and RRF fusion itself are dropped entirely —
"the scope reduction is still explicit, drop use of MedCPT" (operator).

`ALL_ARMS` (`app.eval.ablation_config`) shrinks from 28 (2×2×7) to 4
(2×2×1) — Level 3 no longer varies as a categorical identity; every leaf
configuration sweeps the same `bm25_weight` grid uniformly. The whole
`has_alpha_dimension`/`alpha_values_for`/`BM25_ONLY_ALPHA` machinery that
existed specifically to handle `bm25`'s and the `rrf_*` arms' "no weight
dimension" edge case is removed — nothing left to special-case.

### 12.2 Primary metric: Recall@K, not MRR@K

"The primary evaluation metric should be updated to Recall @K where K is
not hard coded. K should be allowed to range between 2 and 20 with
increments of 2" (operator) — this K range already matched
`ablation_k_values`'s existing default, so no new K-range config was
needed. `PerQueryResult` gains a new `recall_at_k: float` field
(`app.eval.metrics.precision_recall_at_k`, reused unchanged); the
pre-existing `reciprocal_rank_at_k` (MRR) is kept as a **secondary**
metric, not deleted — every `summarize_*` function in
`app.eval.unified_ablation.summary` takes a `metric: Literal["recall",
"mrr"]` selector, defaulting to `"recall"`.

### 12.3 Naming: `alpha` → `bm25_weight`

"Instead of the using the label `alpha` change to `weighted rank` with
w_BM25 ∈ {...}" — resolved directly with the operator as the field name
`bm25_weight` (not `w_bm25` or another form). Renamed in
`PerQueryResult.alpha` → `.bm25_weight`, `ABLATION_ALPHA_VALUES` →
`ABLATION_BM25_WEIGHT_VALUES`, `--alpha-values` → `--bm25-weight-values`
(CLI). The shared `retrieval_tuning.offline_fusion.weighted_rank`
function itself keeps its own `alpha=` parameter name unchanged — it's
shared with `retrieval_tuning`'s own code, which was not part of this
request; only `unified_ablation`'s own call site renamed the concept.

### 12.4 Statistical comparison: a curve, not an arm-vs-reference delta

Level 3 no longer has a "reference arm" to compare others against — it's
one continuous parameter. `summarize_level3`/`summarize_level3_mechanism`
(§11) are both replaced by `summarize_level3_curve`: one `Level3Curve` per
Level-1×Level-2 slice (4 total), each holding the full recall@k curve over
every `bm25_weight` (6 points since §14; 11 when written) plus a
paired-bootstrap delta between the sweep's two endpoints
(`bm25_weight=1.0` vs. `bm25_weight=0.0`) as the headline number — the
natural replacement for "arm vs. reference" now that there's no reference.

### 12.5 Report: back to 3 panels, Panel C redesigned

Panel D (the RRF-vs-alpha-blend mechanism comparison) is gone with RRF.
Panel C is no longer a point-with-CI arm comparison — it's a real line
chart (`bm25_weight` on x, recall@k on y, one line per Level-1×Level-2
slice), mirroring `retrieval_tuning.report.chart_alpha_vs_recall_by_k`'s
own established "swept parameter on x, one line per categorical group"
pattern. A real layout bug (legend + 4-line endpoint-delta annotation
running off the image edge) was found via live visual inspection of the
rendered PNG, not assumed correct from a successful render call, and
fixed with shorter slice labels and wider margins.

### 12.6 Verification

Offline: 695 tests passing (net fewer than §11's 710 — more MedCPT/RRF
tests were deleted than recall/weight tests were added, matching the code
deleted in the same change), same 19 pre-existing unrelated failures.
Live: the restructured pipeline smoke-tested end-to-end against the real
corpus three times while fixing the Panel C layout bug, confirmed no
MedCPT encoder ever loads. **Not yet run at full scale** — pending the
2,500-question ablation-holdout pool (DEVIATIONS #199/#200) finishing
generation. Full account: DEVIATIONS.md #201.

## 13. Statistical rigor extension (2026-09-23, DEVIATIONS.md #202) —
extends §12, does not replace it

Same day as §12's restructuring, the operator specified the exact
statistical comparisons required, at minimum, across all ablation
conditions: paired Δ Recall@K with a 95% CI **and a p-value** for Level 1
and Level 2; the full Recall@k curve (k ∈ {2,4,...,20}) for every one of
Level 3's `bm25_weight` values (11 when written; 6 since §14), with CIs; and an explicit test of
"whether BM25 weighting helps at all," comparing the single best-performing
weight (chosen **after seeing the data**, at a single k also chosen after
seeing the data) against plain BM25 (`bm25_weight=1.0`) — with the
instruction that "the CI/p-value on that specific delta should be
interpreted with that in mind."

### 13.1 p-values on every existing delta

`app.eval.bootstrap.paired_bootstrap_test(scores_a, scores_b, *, rng, ...)`
is a new function alongside the existing `paired_bootstrap_ci_delta` (kept,
unchanged, for callers that only want the CI) — both share one
`_paired_bootstrap_deltas` resampling helper so they can never drift apart
(verified by a test asserting byte-identical CIs given the same seed). The
p-value is the standard two-sided percentile-bootstrap p-value: the
empirical fraction of resampled deltas on the opposite side of zero from
the observed point estimate, doubled, capped at 1.0 — computed from the
**same** resample pass as the CI, not a second independent one.
`summary.DeltaScore` gained a `p_value: float` field via a new shared
`_delta_score` helper, so every existing delta in the module (Level 1,
Level 2, Level 3's endpoints-delta) carries a p-value with no call-site
restructuring beyond the helper swap.

### 13.2 The full Level 3 grid

`summarize_level3_by_weight_and_k(rows, *, k_values, weight_values, ...)`
returns one `WeightKPoint` per (`bm25_weight`, `k`) pair — 60 points at
the default 6-weight × 10-k config (110 at the 11-weight grid in force when
this was written; see §14) — **pooled across Level 1 × Level 2**.
This pooling is a judgment call, not explicitly confirmed with the
operator before implementing (flagged per `DEVIATIONS.md`'s own
append-the-moment-a-call-is-made convention): Level 3 doesn't itself vary
Level 1/Level 2, so the project's existing "marginalize every dimension
not being directly compared" convention extends naturally here, and it
matches the operator's own framing ("at minimum, across all ablation
conditions, calculate...").

### 13.3 The post-hoc best-weight-vs-BM25 test

`summarize_best_weight_vs_bm25(rows, *, k, weight_values, ...)` selects
whichever `bm25_weight` empirically maximizes mean recall@k — a
data-dependent, "cherry-picked" selection, exactly as specified — then
computes a paired delta+CI+p-value between that selected weight and
`bm25_weight=1.0`. The returned `BestWeightVsBM25` dataclass reports
`selected_weight` explicitly (so the selection is never hidden in the
number) and carries an extensive docstring on its own `delta` field
warning about winner's-curse/multiple-comparisons bias — treated as a hard
requirement given the operator's own explicit instruction to interpret
this specific CI/p-value with the selection in mind, not merely a
suggestion to mention it once.

### 13.4 Persistence and CLI

`scripts/run_unified_ablation.py` prints every delta's p-value alongside
its CI, prints the full-grid point count and the post-hoc result
(including its caveat inline in the printed text), and persists all of
it — via `dataclasses.asdict()` — to a new `statistical_summary.json` in
the run directory, alongside the existing `configuration.json`/
`per_query_results.jsonl`. The statistics section of `main()` was factored
into a `_report_statistics()` helper purely to stay under ruff's
statement-count lint limit once the new calls were added.

### 13.5 Deliberately out of scope for this entry

`report.py` is unchanged — the operator's request was for the statistical
calculations themselves (now fully available in stdout and
`statistical_summary.json`), not chart changes. Visualizing the new
statistics (p-value annotations, a grid heatmap, a best-weight marker) is
a plausible follow-on the operator has not asked for.

### 13.6 A flagged pre-existing interaction (not introduced here, not fixed)

`mrr_k()` (the headline `k` used for every Level 1/2/3-endpoints delta)
and `k_values()` (the swept k-grid) are independent config values with no
validation that the former is a member of the latter — established in
§12, surfaced during this entry's own live smoke-testing. Overriding
`--k-values` to a set excluding the headline `k` silently produces
"no data at that k" for every headline delta (`mean_delta=+0.000`,
`p_value=1.0000`), indistinguishable at a glance from a genuine null
result. The shipped default config is unaffected (`mrr_k()=12` is always
inside the default `k_values()=(2,4,...,20)`); not fixed here as it was
out of scope for this entry's request.

### 13.7 Verification

Offline: 705 tests passing (695 + 10 new: 6 in `test_bootstrap.py`, 4 in
`test_unified_ablation_summary.py`), same 19 pre-existing unrelated
failures, `ruff format`/`ruff check`/`mypy` clean on every changed file.
Live: the full CLI smoke-tested against the real corpus with the default
k-grid, producing genuine non-degenerate p-values, a correctly-pooled
30-point grid (reduced weight set for speed), and a `best_weight_vs_bm25`
result correctly resolving to "BM25 is already the best weight" for this
corpus/config (zero delta, p=1.0). `statistical_summary.json` inspected
directly for structure and spot-checked by value. The pre-existing 3-panel
report re-rendered and visually re-inspected — no layout regressions, as
expected since `report.py` was not touched. Full account: DEVIATIONS.md
#202.

## 14. Level 3 weight grid reduced to 0.2 granularity (2026-09-25, DEVIATIONS.md #207) — amends §12.1

The operator revised the Level 3 weighted-rank-fusion sweep to:

```
w_BM25 ∈ {0.0, 0.2, 0.4, 0.6, 0.8, 1.0}
```

6 points instead of §12.1's 11. Both endpoints (pure SapBERT at 0.0, pure
BM25 at 1.0) are kept, so §12.4's endpoints delta and §13.3's
best-weight-vs-BM25 comparison keep the same meaning. §13.2's pooled grid
shrinks from 110 to 60 (weight, k) points, and §13.3's post-hoc selection
now picks the best of 6 empirical means instead of 11 (a smaller
multiple-comparisons penalty, though the winner's-curse caveat still
applies).

The design is otherwise unchanged: Level 1/2 conditions, the K grid
(2–20 step 2), the headline `k` (`mrr_k()=12`), the primary metric
(Recall@K) and the fusion formula. The Level 1 and Level 2 *numbers* do
change, though: both deltas are pooled over `bm25_weight` (§4 point 4's
marginalization convention), so they now average over 6 weights instead
of 11.
The grid is still config-driven — `ABLATION_BM25_WEIGHT_VALUES`, whose
default in `app/config.py` is now `0.0,0.2,0.4,0.6,0.8,1.0`.

**Existing run re-derived, not re-run.** The new grid is a strict subset
of the old one, so run `20260925T064650Z-81570c93`'s per-query rows at
the six retained weights are exactly what a fresh run at the new grid
would produce (retrieval and scoring are deterministic per weight;
bootstrap resampling uses the fixed seed). One side effect:
`summarize_level3_curve` draws every per-weight CI and then the endpoints
delta from a single shared RNG. With fewer weights the endpoints delta
gets a different part of the random stream, so its CI bounds moved by
about 0.0002 while its point estimate stayed identical. Its `statistical_summary.json`,
`unified_ablation_report.png` and `recall_at_k_by_bm25_weight.png` were
regenerated from those rows only. `per_query_results.jsonl` and
`configuration.json` are left as the untouched record of what actually
ran (11 weights).
