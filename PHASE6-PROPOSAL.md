# Phase 6 Checkpoint Proposal — Hybrid Retrieval Weight & Depth Calibration

**Status:** Proposed — awaiting Checkpoint 6 approval. Nothing in this
document has been implemented. Phases 0–5 are complete and
checkpoint-approved (see README.md §Status); this proposes new, additive
work, per the phase-checkpoint protocol in CLAUDE.md §2.

**Proposed requirement IDs:** `PRD-109`, `ARCH-040` (next free slots as of
this draft — confirm against PRD.md/ARCHITECTURE.md before assigning, in
case other work has landed IDs in the meantime).

---

## 1. Motivation

`ARCH-003`/`PRD-010` shipped hybrid retrieval (dense + BM25 + rerank) in
Phase 2, fused server-side via Qdrant's unweighted RRF
(`app/retrieval/vectorstore.py`). That decision was justified qualitatively
(ARCHITECTURE.md's ARCH-003 row) but never measured against alternatives.
This phase produces that measurement: for each already-generated eval
question with a known gold guideline chunk, how often does hybrid search
actually surface that chunk, at what retrieval depth (`k`), and does a
weighted combination of the BM25 and vector scores outperform plain RRF at
any point in that range. The output is evidence, not a production change —
see §7 (Out of scope).

## 2. Architectural constraint this proposal is built around

Production `retrieve()` does not have a BM25/vector weight to sweep.
`QdrantVectorStore.hybrid_search` prefetches dense and sparse candidates
equally and fuses them with `FusionQuery(fusion=Fusion.RRF)`; per
`DEVIATIONS.md` #49, even RRF's own `k` constant isn't exposed through the
client API. **This phase therefore adds a parallel, offline fusion path
used only by the experiment — it does not modify `app/retrieval/hybrid.py`
or `vectorstore.py`, and it writes no `audit.audit_event` rows.** Wiring a
result from this experiment into production is explicitly out of scope here
(§7) and would be its own, separate, later checkpoint.

## 3. Clarification of "known chunk" (interpretation, to be logged)

Simulated questions are generated from **synthetic patient records**
(`app/eval/question_gen/generate.py`, `source_record_id`), but the "known
chunk" they're checked against is the **guideline corpus chunk** the
question's expected answer traces to (`EvalQuestion.gold_relevant_chunks` /
`gold_citations`) — patient records themselves are never embedded or
retrieved (`PATIENT_RECORD_VECTORS_ENABLED=false`, ARCH-023). This reading
will be logged as a `DEVIATIONS.md` entry once this phase starts, since it
resolves an ambiguity in how the requirement was phrased, not something
explicit in the existing docs.

## 4. Deliverables

```
backend/app/eval/retrieval_tuning/
  __init__.py
  offline_fusion.py   # dense-only + sparse-only Qdrant queries, client-side
                       # min-max normalization, weighted combine
  sweep.py             # grid over k x alpha; recall@k / MRR@k via the
                       # existing app.eval.metrics functions (reused, not
                       # reimplemented)
  report.py            # seaborn chart generation, dataviz-skill palette
backend/scripts/run_retrieval_weight_sweep.py   # CLI entry point
backend/tests/test_retrieval_tuning.py          # offline, :memory: Qdrant,
                                                 # EMBEDDING_BACKEND=stub
backend/app/eval/retrieval_tuning/reports/*.png # the three-panel report (DEVIATIONS.md #129)
```

**Eval-set filter:** `EvalQuestion` rows with `expected_outcome ==
well_supported` and non-empty `gold_relevant_chunks` (the other two outcome
classes have no gold chunk and are meaningless for recall/MRR). Uses the
full `auto_generated` pool, not just `in_fixed_testset` rows, for
statistical power — the fixed testset is deliberately small and pinned for
CI stability, which this sweep doesn't need. (Also a judgment call to be
logged in DEVIATIONS.md.)

**Offline fusion mechanics:** per question, two separate Qdrant queries
(`using="dense"` only, `using="sparse"` only) to a generous candidate depth
independent of production's `candidate_k`; min-max normalize each list's
scores within that query's candidate pool (raw BM25 is unbounded, cosine is
bounded — not comparable un-normalized); for each swept `alpha`, combined
score = `alpha * bm25_norm + (1 - alpha) * dense_norm`; re-rank; truncate to
each swept `k`; hand the resulting chunk-id list to the existing
`app.eval.metrics.precision_recall_at_k` / `mrr` unchanged.

**RRF baseline:** the same eval-question set is also run once through the
real, unmodified `retrieve()` (production RRF path) to produce a reference
recall@k / MRR@8 point, plotted alongside the weighted-fusion sweep on all
three charts. This is the number Phase 7's trigger condition (§7) would be
measured against.

## 5. Experiment grid and chart specs

- Depth `k`: {2, 4, 6, 8, 10, 12, 14, 16, 18, 20}
- BM25 weight `alpha`: {0.0, 0.2, 0.4, 0.6, 0.8, 1.0}

**Update (2026-09-17, after the real sweep ran — see DEVIATIONS.md #123):**
widened per follow-up request to `k` ∈ {2, 4, …, 60} (30 values) and `alpha`
∈ {0.0, 0.1, …, 1.0} (11 values). `CANDIDATE_DEPTH` (§4) raised 50 → 100 to
stay comfortably ahead of the new `max(k)=60` — a candidate pool sized
exactly to the deepest `k` would silently cap recall@60 at whatever
recall@candidate_depth already was. Chart 1's alpha coloring changed from 6
categorical hues to an 11-step sequential blue ramp (alpha is an ordered
dial, not a set of unrelated identities, and 11 series is past where the
validated 8-hue categorical order guarantees CVD-safe adjacent separation —
see `report.py`'s module docstring). The real results in `DEVIATIONS.md`
#123 and README.md's Phase 6 entry are from this wider grid, not the
originally-approved one.

**Chart 1** — `k` (x) vs recall@k (y), one line per `alpha`, plus the RRF
baseline as a dashed reference line.
**Chart 2** — `alpha` (x) vs recall@k (y), one line per `k` ∈ {4, 6, 8, 10}
— a re-pivot of Chart 1's data, no new computation.

**Update (2026-09-17, second follow-up request — see DEVIATIONS.md #124):**
Chart 2's focus `k` set widened from {4, 6, 8, 10} to {20, 22, ..., 40} (11
values, still a subset of the already-widened `K_VALUES` grid from the first
update above — no new sweep computation needed). Coloring switched from the
4-slot categorical order to the same 11-step sequential blue ramp chart 1's
`alpha` uses, since 11 series is past the categorical order's validated
CVD-safe count and `k` (retrieval depth) is an ordered dial, same reasoning
as chart 1's original recolor.

**Update (2026-09-17, third follow-up request — see DEVIATIONS.md #125):**
Chart 2's focus `k` set changed again to {3, 6, 9, ..., 36} (12 values, step
3). Unlike the previous update, this set is **not** a subset of `K_VALUES`
(2..60 step 2) — the odd multiples of 3 (3, 9, 15, 21, 27, 33) aren't in that
grid. Rather than widen `K_VALUES` itself (which would have silently
densified chart 1's curves with points nobody asked to add there), chart 2
now has its own independent depth grid, `CHART2_K_VALUES`, computed from the
same per-question rankings with no new Qdrant/embedding calls (truncating an
already-ranked candidate list to any k ≤ `_MAX_K` is free). Still 12 series
→ still past the categorical order's CVD-safe count → still the same
sequential blue ramp as chart 1.

**Update (2026-09-17, fourth follow-up request — see DEVIATIONS.md #126):**
Chart 2's focus `k` set changed again to {4, 8, ..., 36} (9 values, step 4)
— this time a subset of `K_VALUES` again, but `CHART2_K_VALUES` was kept as
a permanently independent constant rather than switching back to reading
`recall_rows` (chart 1's data): the set has now changed three times on
follow-up request, and coupling chart 2's grid to chart 1's grid would mean
re-litigating subset membership (and the risk of silently densifying chart
1) every time it changes again. 9 series is still past the categorical
order's CVD-safe count, so it's still the same sequential blue ramp.

**Chart 3** — `alpha` (x) vs MRR@8 (y), plus the RRF baseline as a dashed
reference line. **`k=8` justification:** `settings.top_k = 8` is the actual
depth production hands to the reranker/synthesis agent
(`hybrid.py`'s `top[: settings.top_k]`), and `eval_min_precision_at_8` is
already the live CI gate in `config.py` — this makes the chart answer the
operationally real question (which `alpha` helps at the depth the system
actually uses) rather than an arbitrary `k`, and keeps it comparable to
numbers the eval harness already reports (`precision_recall_at_k`'s
reporting set is `{5, 8, 24}`).

**Update (2026-09-17, fifth follow-up request — see DEVIATIONS.md #127):**
Chart 3 changed from a fixed `k=8` to `k` = the best-recall depth from
chart 2, i.e. `MRR_K = max(CHART2_K_VALUES)` (36, currently). This
mechanically supersedes the `k=8` justification above for this specific
chart: `recall@k` is monotonically non-decreasing in `k` (a deeper cutoff
of the same ranked list can only match the same gold chunks or more), so
"the k with the best recall" is always chart 2's deepest plotted `k`, not a
per-alpha varying value — there is no other k for "best recall" to resolve
to. Y-axis changed from the dynamic 0.3-floor (charts 1/2) to a fixed
0.0-1.0 range with ticks every 0.1: 0.0 is MRR's true floor (it cannot be
negative), so a fixed range here doesn't risk hiding real data the way a
fixed 0.3 floor did before the #122 fix. Confirmed with the user before
implementing that "best recall k" is mechanically constant across alpha
(not a per-alpha varying k), given the monotonicity above.

**Update (2026-09-17, sixth follow-up request — see DEVIATIONS.md #128):**
Chart 3's `k` changed again, this time to a direct, explicit value: `MRR_K
= 24` (a member of `CHART2_K_VALUES`), no longer derived from "best recall"
at all. The chart's PNG output was renamed a second time to a
value-agnostic `chart3_alpha_vs_mrr.png` (was `chart3_alpha_vs_mrr_best_k.png`,
originally `chart3_alpha_vs_mrr8.png`) — this depth has now moved three
times on follow-up request (8 → 36 → 24), and a filename encoding the
specific k value would need renaming every time it changes again; the chart
function itself (`chart_alpha_vs_mrr`, dropped "_at_best_k") and its
title/axis label already read `MRR_K` dynamically, so they render correctly
whatever the constant is set to.

**Update (2026-09-17, seventh follow-up request — see DEVIATIONS.md #129):**
The three charts are no longer three separate PNGs. They now render as
stacked panels (A/B/C, top to bottom, each panel-labeled) in one combined
figure, `retrieval_tuning_report.png`, sized 18cm (w) x 21cm (h) at 600dpi
— both per explicit follow-up request. `chart_*` functions draw onto a
caller-supplied `Axes` instead of creating and saving their own `Figure`;
`generate_reports` owns the single `Figure`/`savefig` call and returns a
one-element path list. Marker sizes, line widths, and font sizes were
reduced from the original per-chart values to stay legible in the smaller
per-panel area (~18cm x 7cm each); legends stayed outside each panel's axes
to the right, with chart 2's per-entry text shortened (`k=4` instead of the
full `"k=4 (dotted = RRF baseline at that k)"`) and the explanation moved to
a short legend title instead, to fit the narrower reserved margin.

All charts: seaborn, `dpi=600` (was 300 — DEVIATIONS.md #129), written to
`backend/app/eval/retrieval_tuning/reports/`. Chart code will load the
`dataviz` skill before writing (per that skill's own trigger condition).

## 6. Compliance with CLAUDE.md §3

- **No PHI:** source records are the existing `synthetic-generator-v1`
  output only; the guideline corpus isn't patient data. No new data source.
- **No hardcoded models:** reuses `embed_texts` / `query_sparse_vector`
  as-is, both already config-driven. No new model reference introduced.
- **Determinism:** the sweep's metrics (`precision_recall_at_k`, `mrr`) are
  already plain code, consistent with "grounding/confidence/citation
  resolution is deterministic, not model calls."
- **No production path touched:** `hybrid.py` / `vectorstore.py` are
  unmodified; no new `audit.audit_event` writes; no change to what any live
  endpoint returns.
- **CDS boundary:** not implicated — this is retrieval-depth/weight
  calibration, not next-step recommendation or guideline adjustment.

## 7. Out of scope for Phase 6

**Not included:** any change to production fusion (`hybrid.py`,
`vectorstore.py`), `config.py` additions for a weighted-fusion mode, or any
change to what `retrieve()` returns. If the sweep in this phase shows a
fixed `alpha` that beats the RRF baseline *robustly* — consistently ahead
across `k` ∈ [4, 10], not just at one cell, and stable across a couple of
random splits of the eval-question pool — that becomes the trigger for a
**separate Phase 7 proposal** ("Production Fusion-Weight Adoption"),
requiring its own checkpoint, its own `ARCH` revision (extends/partially
supersedes ARCH-003), and re-running the full gating-test suite
(`test_scope_boundary.py`, `no_guideline_expected` grounding cases,
`disclaimer_present_rate`, `test_audit_append_only.py`) under the new fusion
path before it could ever become a default. That proposal already has a
draft outline from this conversation (client-side weighted combine
recommended over Qdrant's server-side `FormulaQuery`, due to an open
qdrant-client 1.19 bug combining `FormulaQuery` with multi-vector prefetch —
qdrant/qdrant-client#1072); it will be written up as `PHASE7-PROPOSAL.md`
only if Phase 6's results actually trigger it.

## 8. Testing plan

- `backend/tests/test_retrieval_tuning.py`: a small fixture corpus (a
  handful of chunks), embedded Qdrant `:memory:`, `EMBEDDING_BACKEND=stub` —
  same pattern as `test_hybrid_retrieve.py` — validates the sweep's
  normalize/combine/rank arithmetic on a tiny 2×2 (`k`, `alpha`) grid. This
  runs in `make test` (offline, no network, per CLAUDE.md §5).
- The full grid over the real eval-question pool (§4) is a manual/CI-optional
  target (e.g. `make retrieval-tuning-report`), not part of the pytest
  gating suite — it's analysis tooling producing a report, not a shipped
  safety gate.

## 9. Docs updated in the same change (once approved and implemented)

- `TRACEABILITY.md`: new rows for `PRD-109` / `ARCH-040`.
- `README.md`: Status table gets a Phase 6 row; §Status prose gets a short
  paragraph describing the deliverable, matching the style of Phases 1–5.
- `DEVIATIONS.md`: entries for the "known chunk" interpretation (§3) and the
  "full auto_generated pool vs fixed testset" choice (§4), logged the moment
  this phase starts, not retroactively.

---

**Checkpoint 6:** Stop here. Do not begin implementation until this
proposal is explicitly approved — including the scope boundary in §7 (no
production fusion change without a separate Phase 7 checkpoint).
