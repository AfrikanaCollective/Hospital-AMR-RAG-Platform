# Phase 2 Evidence-Gathering Proposal — Biomedical Embedding Ablation (SapBERT / MedCPT)

**Status:** Proposed — awaiting checkpoint approval. Nothing in this
document has been implemented. Phases 0–5 are complete and
checkpoint-approved (README.md §Status); Phase 6 (BM25/vector weight & depth
calibration, `PHASE6-PROPOSAL.md`) is also approved and complete. This
proposes new, additive, **offline-only** work in the same spirit as Phase 6
— it does **not** reopen Phase 2 itself. Reopening Phase 2 (changing
`app/retrieval/hybrid.py` / `vectorstore.py` / ingestion to actually serve
SapBERT/MedCPT in production) would be its own, later, separate proposal —
this one only gathers the evidence that would justify (or rule out) that
step, per the phase-checkpoint protocol in CLAUDE.md §2.

**Proposed requirement IDs:** `PRD-110`, `ARCH-041` (next free slots as of
this draft, confirmed against `TRACEABILITY.md` — re-confirm at
implementation time in case other work has landed IDs in the meantime).

---

## 1. Motivation

The user asked whether general-purpose embeddings (currently
`BAAI/bge-large-en-v1.5`, ARCH-004) miss clinically-related terms that a
biomedical-specific model would catch — the standing example is *large
bowel* / *colorectal*, terms a general embedding model may not place as
close as a model trained on biomedical entity linking or clinical query-
article relevance would. Two candidate models were named:

1. **SapBERT** (`cambridgeltl/SapBERT-from-PubMedBERT-fulltext` — **name and
   pooling method UNVERIFIED against the model's current card; see §6**), a
   symmetric encoder trained for biomedical entity linking / synonym
   clustering (UMLS-based contrastive training) — the "large bowel ~
   colorectal" case is exactly its training objective.
2. **MedCPT** (`ncbi/MedCPT-Query-Encoder` + `ncbi/MedCPT-Article-Encoder` —
   **names and pooling method UNVERIFIED; see §6**), an *asymmetric*
   dual-encoder trained on real PubMed query-article click logs for
   clinical semantic relevance, i.e. a different query checkpoint from its
   document checkpoint (not a single shared model).

Before touching production retrieval (Phase 2) or its fusion strategy
(ARCH-003) with either model, this phase answers a narrower, cheaper
question first: **does adding SapBERT and/or MedCPT alongside BM25 actually
find more of the known gold guideline chunks, on this deployment's own
corpus and eval-question set, than what's already measured?** This mirrors
Phase 6's own relationship to a hypothetical "Phase 7" (PHASE6-PROPOSAL.md
§7): produce evidence first, decide whether to act on it second, as a
separate, later checkpoint.

## 2. Why this is materially smaller/safer than reopening Phase 2

The live guideline collection has **314 points** (confirmed via
`QdrantVectorStore` against the running `dev` stack, 2026-09-17) — small
enough to embed and rank *exactly* (brute-force cosine similarity, no ANN)
entirely in memory, once per ablation run. Consequently this phase:

- **Adds no new named vectors to the Qdrant collection.** SapBERT/MedCPT
  embeddings are computed in-memory for the duration of one script run and
  discarded — never upserted, never persisted. No collection schema change,
  no re-ingestion.
- **Touches no production path.** `app/retrieval/hybrid.py`,
  `vectorstore.py`'s `hybrid_search`, and `app/ingestion/embed.py` are not
  imported or modified by this module, same discipline as Phase 6
  (PHASE6-PROPOSAL.md §2).
- **Writes no `audit.audit_event` rows** and touches no patient data — the
  eval-question set already exists (`EvalQuestion.gold_relevant_chunks`,
  fixed/backfilled in DEVIATIONS.md #122) and the guideline corpus isn't
  patient data.
- **Reuses, rather than rebuilds, Phase 6's harness**:
  `app.eval.retrieval_tuning.sweep.fetch_calibration_questions` (67
  `well_supported`/`auto_generated` questions with real gold chunks) and
  `app.eval.metrics.precision_recall_at_k`/`mrr`, unchanged.

## 3. What's genuinely new here (vs. Phase 6)

Phase 6 swept a weight between two **already-embedded, already-in-Qdrant**
signals (the production dense model + the production sparse/BM25 vector).
This phase needs two encoders that have **never been embedded for this
corpus at all**:

- **New optional dependency, but no new package**: `sentence-transformers`
  (already in the `local-models` extra, `backend/pyproject.toml`) pulls in
  `transformers`, which is sufficient to load SapBERT/MedCPT's raw
  checkpoints via `AutoModel`/`AutoTokenizer` — neither is packaged as a
  ready-made `SentenceTransformer` model, so this needs a small manual
  pooling adapter (`[CLS]`-token or mean-pool, exact method **to be
  confirmed against each model's current card at implementation time, not
  guessed** — see §6), not a new dependency.
- **MedCPT's asymmetry must be handled explicitly**: the corpus's 314
  chunks get embedded with the *article* checkpoint, the 67 eval
  questions with the *query* checkpoint — two loaded models for one
  logical "channel," unlike every other channel in this codebase so far
  (BM25/sparse and the production dense model are both symmetric).
- **New config surface** (rule CLAUDE.md §3.5 — no hardcoded model names):
  placeholder settings for the two (or three, counting MedCPT's pair)
  model ids, each with its own `_verified: bool = False` flag and a
  startup/run-time warning when unverified, matching the existing
  `embedding_model_id`/`embedding_model_verified` pattern in `config.py`.
  Proposed additions (all analysis-tooling-only, not read by any
  production code path):
  ```
  SAPBERT_MODEL_ID          (placeholder, unverified)
  SAPBERT_MODEL_VERIFIED    (bool, default false)
  MEDCPT_QUERY_MODEL_ID     (placeholder, unverified)
  MEDCPT_ARTICLE_MODEL_ID   (placeholder, unverified)
  MEDCPT_MODEL_VERIFIED     (bool, default false)
  ```
  An unverified model id logs a warning and proceeds anyway for this
  analysis tooling (it is not a shipped safety gate, same framing as
  PHASE6-PROPOSAL.md §8) — unlike `MODEL_ID_VERIFIED=false` on the real
  answer path, which blocks.
- **One new `QdrantVectorStore` method**: `scroll_all(with_payload=True) ->
  list[dict]`, to fetch all 314 chunks' `id`/`text` once per run (Qdrant's
  native `scroll` API, paginated internally). Used only by this ablation
  tooling, same justification pattern as Phase 6's `single_vector_search`
  addition (DEVIATIONS.md #121) — not added to the `VectorStore` Protocol,
  since production code never calls it.

## 4. Deliverables

```
backend/app/eval/model_ablation/
  __init__.py
  encoders.py      # SapBERT / MedCPT loading + pooling; a "stub" mode
                    # (deterministic fake vectors, no download) for offline tests
  ablation.py       # brute-force in-memory embed + rank + RRF-combine across
                    # the 3 requested arms, reusing app.eval.metrics unchanged
  report.py         # chart(s), dataviz-skill palette, same conventions as
                    # app.eval.retrieval_tuning.report
backend/scripts/run_model_ablation.py   # CLI entry point (Makefile target
                                          # `make model-ablation-report`)
backend/tests/test_model_ablation.py    # offline, stub encoders, no network,
                                          # no model download — per CLAUDE.md §5
```

## 5. Experiment design

**Corpus & questions:** the same 314-chunk live guideline collection and
the same 67 `well_supported`/`auto_generated` calibration questions Phase 6
uses (`fetch_calibration_questions`) — no new data, no new PHI exposure.

**Channels:**
- **BM25**: the existing `sparse` named vector already in Qdrant, queried
  via `single_vector_search(using="sparse", ...)` (unchanged from Phase 6).
- **SapBERT**: one symmetric checkpoint, chunks and questions embedded the
  same way, ranked by cosine similarity over the full in-memory 314-vector
  pool (no candidate-depth truncation needed — see §2).
- **MedCPT**: query checkpoint for questions, article checkpoint for
  chunks, same brute-force cosine ranking.

**Combination method:** **RRF-by-rank as the primary comparison** — each
channel produces a full ranking over all 314 chunks; combine by rank
position (Qdrant's own RRF formula, reimplemented client-side since there's
no Qdrant collection to run it against here), not a weighted score blend.
Rationale: RRF is what production actually does today (ARCH-003) between
its two channels, so this is the most directly comparable question ("if we
added these channels to today's fusion, roughly what happens") without also
introducing a new weight parameter to justify. Phase 6's weighted min-max
combine machinery (`offline_fusion.py`) generalizes to N channels if a
follow-up wants to sweep weights too, but that's proposed as an **optional
second pass**, not part of this proposal's v1, to keep scope bounded.

**Ablation arms** (per the user's request), each measured at the same k
grid and reference k Phase 6 established, for direct comparability:
1. SapBERT + BM25 (RRF)
2. MedCPT + BM25 (RRF)
3. SapBERT + MedCPT + BM25 (RRF, 3-way)

**Reference points already on hand (no new computation):** production's
real RRF baseline (bge-dense + BM25) and the best point from Phase 6's own
alpha sweep — both already measured and reported in
`DEVIATIONS.md` #122/#123. Plotting the three new arms alongside these two
existing numbers is what actually answers "is a biomedical model worth
it," not the three new arms in isolation.

**Metrics & charts:** reuse `precision_recall_at_k`/`mrr` unchanged.
Proposed default: recall@k vs. k (one line per arm, plus the two reference
points) at the same depths Phase 6 already swept, and a second panel/chart
at the production-relevant `k=24` (matching the current `MRR_K`,
DEVIATIONS.md #128) for MRR — but exact chart layout is expected to get
refined interactively after a first real render, same as every chart in
Phase 6 did over several follow-up rounds.

## 6. Explicitly flagged uncertainty (not guessed silently)

- **Exact HuggingFace repo ids** for SapBERT/MedCPT above are my best
  knowledge, not verified against current model cards. Per CLAUDE.md §3.5,
  they'll be checked against current documentation before the first real
  (non-stub) run, and the `_verified` flags above default to `false` until
  that check happens.
- **Exact pooling method** (`[CLS]`-token vs. mean-pooling, any
  L2-normalization) for each encoder will be confirmed against that model's
  own card/reference implementation at implementation time — getting this
  wrong doesn't crash anything, it just silently produces a worse embedding
  than the model is capable of, so it needs deliberate verification, not an
  assumption carried over from the bge/sentence-transformers pattern
  already in `embed.py`.

## 7. Compliance with CLAUDE.md §3

- **No PHI:** same corpus/question set as Phase 6 — guideline text isn't
  patient data; synthetic patient records aren't touched.
- **No hardcoded models:** new placeholder config per §3 above, each
  flagged unverified until checked; no model id is assumed correct.
- **No production path touched:** `hybrid.py`/`vectorstore.py`'s
  `hybrid_search`/`ingestion/embed.py` are unmodified; the one new
  `QdrantVectorStore` method (`scroll_all`) is additive and read-only.
- **Determinism:** the RRF-combine and metrics are plain code; only the
  embedding calls themselves are model calls (same split Phase 6 already
  established).
- **CDS boundary:** not implicated — this is retrieval-signal evaluation,
  not next-step recommendation or guideline adjustment.

## 8. Out of scope for this proposal

**Not included:** any change to production fusion, ingestion, or the
Qdrant collection schema; any new named vectors persisted anywhere; a
weighted (non-RRF) sweep across the three arms (proposed only as an
optional later pass, §5); and — the big one — **actually reopening Phase 2**
to serve SapBERT/MedCPT in production. If this ablation shows either model
robustly improves recall/MRR over the current RRF baseline, that becomes
the trigger for a **separate Phase-2-reopening proposal**, with its own
checkpoint, its own `ARCH-003` revision, new production config
(non-placeholder, verified model ids), an ingestion re-embed pass over the
real corpus, and a full re-run of the gating safety suite
(`test_scope_boundary.py`, `no_guideline_expected` grounding cases,
`disclaimer_present_rate`, `test_audit_append_only.py`) under the new
fusion path — none of which happens here.

## 9. Testing plan

- `backend/tests/test_model_ablation.py`: a tiny fixture corpus (a handful
  of chunks) and **stub encoders** — `encoders.py`'s stub mode returns
  deterministic fake vectors with no model download and no network call,
  same discipline as `EMBEDDING_BACKEND=stub` elsewhere — validates the
  brute-force ranking and RRF-combine arithmetic. Runs in `make test`
  (offline, per CLAUDE.md §5).
- The full run against the real 314-chunk corpus and real SapBERT/MedCPT
  checkpoints (`make model-ablation-report`) is manual/CI-optional analysis
  tooling, not part of the pytest gating suite — same status as
  `make retrieval-tuning-report`.

## 10. Docs updated in the same change (once approved and implemented)

- `TRACEABILITY.md`: new row for `PRD-110`/`ARCH-041`.
- `README.md`: a new dated entry describing the deliverable, matching
  Phase 6's narrative style.
- `DEVIATIONS.md`: entries for the RRF-only-as-v1 choice (§5), the
  brute-force-in-memory-instead-of-persisted-vectors choice (§2), and
  whatever the actual verified model ids/pooling methods turn out to be
  (§6), logged the moment each is decided, not retroactively.

---

**Checkpoint:** Stop here. Do not begin implementation until this proposal
is explicitly approved — including the scope boundary in §8 (no production
change, no Phase 2 reopening, without a separate later checkpoint).
