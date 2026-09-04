# DEVIATIONS.md — Judgment-Call Log

**Append-only.** Never edit or delete a past entry. When a decision is
reversed, add a **new** entry that references the old one.

Log an entry whenever a judgment call is made that is **not** explicitly
resolved by [PRD.md](PRD.md) / [ARCHITECTURE.md](ARCHITECTURE.md): an ambiguous
requirement interpreted one way, an edge case handled without instruction, or a
default chosen where the spec was silent. Log at the moment the call is made,
not retroactively. When in doubt, log it.

**Entry format**

```
### <n>. <short title>
- **Date / phase:** YYYY-MM-DD / Phase N
- **Requirement ID(s):** PRD-### / ARCH-### / SCOPE-#.# / — (none)
- **Ambiguous or undecided:** what the spec left open or unclear
- **Decision & rationale:** what was chosen and why
- **Reversible?:** yes / partially / no — and what reversal would cost
```

---

## Phase 0

### 1. Vector store: Qdrant chosen over ChromaDB
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-002, PRD-104
- **Ambiguous or undecided:** The brief said "ChromaDB or Qdrant — pick one and justify it."
- **Decision & rationale:** Qdrant. Native dense+sparse hybrid with server-side RRF fusion, fast payload filtering (needed to enforce access scope *inside* the query, which is security-relevant here), and stronger production/operational features. Chroma is simpler but weaker on native sparse/hybrid and large-scale filtering. Full justification in ARCHITECTURE.md §3.
- **Reversible?:** partially — a `VectorStore` adapter interface is planned; swapping to Chroma would mean losing native sparse/hybrid and re-implementing fusion, plus a re-index. Cost: moderate.

### 2. Inter-rater reliability metric: Krippendorff's alpha (ordinal)
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-021, PRD-044
- **Ambiguous or undecided:** Brief said "pick one and justify it (e.g. Krippendorff's alpha or an ICC variant)."
- **Decision & rationale:** Krippendorff's alpha with the ordinal difference function, per rubric domain. Handles a variable, non-fixed rater panel (raters self-select items from the queue), ordinal 5-point data, and missing values — none of which Cohen's/Fleiss' kappa or interval ICC handle cleanly. Gwet's AC2 and ICC(2,k) are computed as *secondary* descriptive statistics. Full justification in ARCHITECTURE.md §14.4.
- **Reversible?:** yes — all raw scores are stored structurally; any metric can be recomputed retrospectively.

### 3. Relational store: PostgreSQL as single system of record
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-008
- **Ambiguous or undecided:** The brief specified FastAPI, Redis/Celery, a vector store, and LangGraph, but did not name an RDBMS. A relational store is needed for HITL/rubric/audit/memory transactional integrity.
- **Decision & rationale:** PostgreSQL, one database with multiple schemas (`corpus`, `records`, `memory`, `hitl`, `eval`, `audit`, `iam`). Reasons: transactional integrity across the rubric/HITL/audit workflow, JSONB for semi-structured payloads, row-level security for PHI scoping, `pgcrypto` for field encryption, and a supported LangGraph Postgres checkpointer.
- **Reversible?:** partially — schema migrations would be needed to move to another RDBMS; the ORM layer abstracts most of it. Cost: moderate.

### 4. Auth: seeded dev-JWT for MVP instead of a full OIDC IdP
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-011, PRD-086
- **Ambiguous or undecided:** PRD-086 requires RBAC with clinician/reviewer/admin roles but does not mandate a specific IdP; "production-grade patterns, minimal feature surface" (PRD-C5) pulls against standing up Keycloak now.
- **Decision & rationale:** An `AuthProvider` interface with a seeded signed-JWT issuer for dev (roles included) plus an OIDC adapter **stub**. Keycloak is available only in the `full` docker-compose profile. Keeps the seam without the MVP operational cost.
- **Reversible?:** yes — the OIDC adapter is a drop-in; no data migration.

### 5. Encryption: envelope-encrypt free-text/blob PHI fields; inter-service TLS partial
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-031, ARCH-032, PRD-082, PRD-083
- **Ambiguous or undecided:** "Encryption at rest and in transit" is mandated as core, but the spec does not define the granularity (per-column field encryption vs blob) or whether mTLS between every internal service is required for a single-host self-hosted MVP.
- **Decision & rationale:** At rest — host volume encryption (documented deployment prerequisite) **plus** application-level envelope encryption for the free-text / blob PHI fields enumerated in ARCHITECTURE.md §17.2; structured record fields live inside the encrypted `payload_enc` blob and are served via the record accessor rather than as individually-encrypted columns. In transit — TLS at the reverse proxy, a private compose network with authenticated Postgres/Redis/Qdrant, and inter-service TLS where the image supports it trivially; full mTLS between every service is documented as a production hardening item, not done in the MVP. The `CryptoProvider` abstraction stays so per-column encryption can be added later.
- **Reversible?:** yes — additive hardening; no data model change to add more encrypted columns or mTLS later.

### 6. Audit tamper-evidence: prev-hash chain only; no external anchoring in MVP
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-035, PRD-085
- **Ambiguous or undecided:** "Immutable audit logging" is mandated; the spec does not specify the mechanism or whether external timestamping/anchoring is required.
- **Decision & rationale:** Append-only enforced by DB grants (`INSERT, SELECT` only for the app role; no `UPDATE`/`DELETE`), plus a `prev_hash`/`row_hash` chain and a chain-verifier job. External timestamping/anchoring to an independent service is deferred as over-engineered for the MVP (self-critique §21c).
- **Reversible?:** yes — anchoring can be layered on later without changing existing rows.

### 7. Stage-classifier and missing-info kept as distinct agents (not merged into synthesis)
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-016, SCOPE-2.1, SCOPE-2.2
- **Ambiguous or undecided:** These two functions could be implemented as prompt modes / tools on the guideline-synthesis agent, which would be fewer moving parts (PRD-C5 favours minimal surface).
- **Decision & rationale:** Kept as separate LangGraph agents with their own tool allow-lists and audit outcomes. Rationale: the SCOPE boundary (in-scope classification/clarification vs. excluded next-step recommendation) must be legible and independently testable; a merged agent makes it easy to accidentally let patient data + guidelines flow into a recommendation. The extra structure is a deliberate safety cost.
- **Reversible?:** yes — could be collapsed later, but the boundary tests would need re-homing.

### 8. Patient-record vectorization OFF by default
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-023, PRD-NFR-5, PRD-080
- **Ambiguous or undecided:** The brief mentions patient records "via flat file or API" and hybrid retrieval, but does not say whether patient-record content is embedded/retrieved like documents.
- **Decision & rationale:** SCOPE-2 flows read structured record fields directly and match them against retrieved *guideline* criteria; patient records are **not** embedded. A `PATIENT_RECORD_VECTORS_ENABLED=false` flag gates any future record vectorization, which if enabled would use a separate Qdrant collection with mandatory `patient_id` payload filtering. Minimises PHI surface.
- **Reversible?:** yes — flag + separate collection; additive.

### 9. "Hard cases" defined as missing_info_expected + no_guideline_expected combined
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-022, PRD-065
- **Ambiguous or undecided:** The brief says hard/adversarial cases "must not exceed 50%" and to use a 60/20/20 split, but does not define precisely which buckets count as "hard".
- **Decision & rationale:** "Hard/adversarial" = `missing_info_expected` + `no_guideline_expected` combined. Under the mandated 60/20/20 split that is 40%, satisfying the ≤50% cap with margin. The set planner enforces both the split and the cap.
- **Reversible?:** yes — composition is a config value (`QGEN_COMPOSITION`) and regeneration is cheap.

### 10. Constraint #6 (no hardcoded model) extended to embedding and reranker models
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** PRD-101, PRD-103, ARCH-004, ARCH-012
- **Ambiguous or undecided:** Constraint #6 names "the LLM". It is silent on the embedding model and the reranker, which are also model identifiers that would otherwise be hardcoded.
- **Decision & rationale:** Applied the same rule: `EMBEDDING_MODEL_ID` and `RERANKER_MODEL_ID` come from config with placeholder defaults (`BAAI/bge-large-en-v1.5`, `BAAI/bge-reranker-v2-m3`), both explicitly marked **UNVERIFIED — flagged** pending operator confirmation. The code contains no model name it depends on.
- **Reversible?:** yes — config only.

### 11. "Three HITL modes" interpreted as: rank axis + accept axis (full/partial/reject)
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-018, ARCH-019, PRD-031, PRD-032
- **Ambiguous or undecided:** The brief says "the three HITL interaction modes required: multi-dimensional output ranking, full accept, partial accept, and reject" — which lists four things but calls them three modes.
- **Decision & rationale:** Modelled as **two independent axes** captured in one review sitting (`rating_round`): (1) **rank mode** = the 11-domain rubric; (2) the **accept axis** with three actions — full accept / partial accept / reject. Rank and accept are independent and both recorded; "three modes" is read as the three accept-axis actions, with ranking as the separate structured-evaluation mode. Both axes' effects on state are defined in ARCHITECTURE.md §13.
- **Reversible?:** yes — data model stores the axes separately; presentation can be re-grouped.

### 12. Conversation hot-state in Redis; durable memory + LangGraph checkpoints in Postgres
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-016, ARCH-017, PRD-022, PRD-023
- **Ambiguous or undecided:** PRD-022 requires persistent memory and names categories but not the storage split; "where it lives" was left to design.
- **Decision & rationale:** Durable conversation/message/patient_context in Postgres (system of record); Redis holds only the active window, streaming partials, and counters with a TTL and is authoritative only until persisted; LangGraph uses the Postgres checkpointer so long runs survive restarts and are inspectable.
- **Reversible?:** yes.

### 13. Citation "chunk offset" realised as chunk_id + char span + section path + page
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-014, PRD-011
- **Ambiguous or undecided:** Constraint #4 requires "document ID + page/section + chunk offset, minimum" without defining "chunk offset".
- **Decision & rationale:** "Chunk offset" is implemented as the `chunk_id` (the atomic retrieved unit) plus `char_start`/`char_end` offsets within the normalized document text, alongside `section_number`/`section_path` and `page_start`/`page_end`, and a verbatim `quote` with its own offsets for highlight + grounding re-verification.
- **Reversible?:** yes — additive fields; the minimum set is a subset.

### 14. No reviewer available for an escalation → hold + safe templated message, no auto-release
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-018 (`ESCALATION_SLA_MINUTES`), PRD-Q2
- **Ambiguous or undecided:** The brief defines escalation triggers but not the behaviour when no human reviewer is available within a reasonable time (e.g. after hours).
- **Decision & rationale:** The escalation stays `open`; the clinician sees a held state with a safe templated message ("this response needs clinician review before it can be shown; no independent recommendation is available"); the candidate answer is **not** auto-released. Fail-safe over fail-open, consistent with PRD-NFR-2.
- **Reversible?:** yes — the SLA and the fallback behaviour are config/policy.

### 15. Cohort / multi-patient questions out of scope; one patient per conversation
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** PRD-NG-011, ARCH-016
- **Ambiguous or undecided:** The brief centres on patient-level records and hypotheticals but does not explicitly address cohort/population queries.
- **Decision & rationale:** A conversation is bound to at most one `patient_id`; cohort/population/cross-patient analytic queries are rejected by the orchestrator. Reduces PHI surface and keeps the grounding/scope model simple for the MVP.
- **Reversible?:** partially — enabling cohorts would need memory-model and access-control changes.

### 16. Ingestion refuses batches that fail a "looks like real data" heuristic
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** PRD-081, PRD-C1
- **Ambiguous or undecided:** "No real PHI, ever" is a policy; the brief does not require a technical control to detect accidental real-data ingestion.
- **Decision & rationale:** Added a warning-level heuristic (e.g. entropy/plausibility checks on names/identifiers) that hard-errors an ingestion batch it suspects is real. This is defence-in-depth, not a guarantee; the policy prohibition remains the primary control.
- **Reversible?:** yes — the check is a toggle and is heuristic only.

### 17. Straight-lining / low-variance rater rule deferred (scores still count for now)
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH-020, PRD-042
- **Ambiguous or undecided:** The multi-rater workflow does not say how to handle a rater who gives near-identical scores across all domains (possible fatigue/inattention), which affects IRR.
- **Decision & rationale:** For Phase 0/1, such raters are **flagged for QA** but their scores **still count** toward the 3-rater minimum and IRR. A concrete exclusion/weighting rule is deferred to when real rating data exists; this entry will be superseded by a new one when the rule is set.
- **Reversible?:** yes — raw scores are retained; any rule can be applied retrospectively.

### 18. Unit / locale normalization not attempted in MVP
- **Date / phase:** 2026-08-27 / Phase 0
- **Requirement ID(s):** ARCH (self-critique §21b), SCOPE-2.1, SCOPE-2.2
- **Ambiguous or undecided:** Patient-record field units may differ from guideline-criteria units (e.g. mg/dL vs mmol/L); the brief does not address unit conversion.
- **Decision & rationale:** The MVP assumes a single-locale English corpus and does **not** perform unit conversion. A unit mismatch between a record field and a criterion surfaces as `missing_critical_info` / `phi_ambiguity` (i.e. "cannot confirm") rather than a silent conversion. Silent conversion is a known error source and is out of scope.
- **Reversible?:** yes — a normalization layer can be added; until then the fail-safe behaviour holds.

---

## Phase 1

### 19. TRACEABILITY.md records non-goals / assumptions / open questions as `deferred`, not `not started`
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** PRD-NG-*, PRD-A*, PRD-Q* (all)
- **Ambiguous or undecided:** The brief says "populate [TRACEABILITY.md] now with every ID from Phase 0, status `not started`". Non-goals, assumptions, and open questions have IDs but are not things to build, so `not started` misrepresents them.
- **Decision & rationale:** The main matrix (functional/NFR/constraint/goal/ARCH/SCOPE) is populated with `not started` per the brief. Non-goals/assumptions/open-questions go in a separate section (§4) as `deferred` with a one-line disposition. This keeps a single matrix without implying unbuilt work for decisions that are deliberate exclusions.
- **Reversible?:** yes — cosmetic; rows can be merged/relabelled.

### 20. Repository layout and tooling choices
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** ARCH-001, ARCH-008, ARCH-010, PRD-100, PRD-107
- **Ambiguous or undecided:** ARCHITECTURE.md fixes the components but not the exact folder layout or the lint/type/test/migration tooling.
- **Decision & rationale:** Monorepo with `backend/` (FastAPI + Celery + agents + all Python) and `frontend/` (Vite + React + TS); Python module tree mirrors ARCHITECTURE.md §2/§4/§10. Tooling: ruff (format + lint), mypy, pytest, Alembic, SQLAlchemy 2.0 declarative one-module-per-schema, pydantic-settings for config, Vite + TS + react-router for the UI. All are conventional choices where the spec was silent.
- **Reversible?:** yes — layout can be refactored; tooling is swappable.

### 21. Synthetic data carries a provenance marker that the real-data heuristic trusts
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** PRD-006, PRD-081, PRD-C1 (relates to DEVIATIONS #16)
- **Ambiguous or undecided:** DEVIATIONS #16 adds an ingestion heuristic that rejects "real-looking" batches. That heuristic would also reject the project's own synthetic data if it uses realistic (Faker) names.
- **Decision & rationale:** `scripts/generate_synthetic_records.py` stamps every record and batch with `dataset_provenance = "synthetic-generator-v1"` (`SYNTHETIC_PROVENANCE`). `app.ingestion.records.looks_like_real_data` returns `False` immediately for a batch bearing that marker, and runs the heuristic only on unmarked batches. Synthetic MRNs are additionally prefixed `SYN-`. The policy prohibition on real data remains the primary control; this is a usability carve-out, not a weakening.
- **Reversible?:** yes — the marker check is one branch; the heuristic still guards everything unmarked.

### 22. `fetch_sample_guidelines` generates synthetic guideline docs offline by default
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** PRD-006, PRD-106, PRD-G7, PRD-A2
- **Ambiguous or undecided:** The brief allows "a handful of sample government/clinical PDFs (or a script that fetches public sample guideline docs)". Requiring a network fetch would break the "core flows work offline" goal for a fresh checkout.
- **Decision & rationale:** The script's **default** is to generate three small **synthetic** guideline documents (clearly marked "NOT CLINICAL GUIDANCE") as Markdown, with numbered sections, recommendation statements (strength/evidence tags), a criteria table, and one deliberately narrow topic — enough to exercise ingestion, chunking, retrieval, citations, stage criteria, and the "no guideline found" path. A `--urls-file` path to download real public PDFs is stubbed for Phase 2. Phase 1 docs are Markdown; the PDF parsing pipeline lands in Phase 2 and will also accept `.md`.
- **Reversible?:** yes — real PDFs can be dropped into `data/sample_guidelines/` at any time.

### 23. Patient-record schema fixed at v1.0.0, explicitly refinable in Phase 2
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** PRD-002, PRD-003, PRD-A3
- **Ambiguous or undecided:** PRD-A3 assumes the record schema is "stable enough to fix in Phase 1", but the real field set was not specified.
- **Decision & rationale:** `backend/app/schemas/record.py` fixes a representative schema (`SCHEMA_VERSION = "1.0.0"`): identity, encounter/care-setting, problems, allergies, medications, vitals series, lab results (with units + reference ranges), free-text notes, consent flags. `data/record_schema.json` mirrors it. This is sufficient to scaffold ingestion, `field_index`, stage criteria, and missing-info. Field refinements in Phase 2 bump `SCHEMA_VERSION` and are logged as new deviations.
- **Reversible?:** partially — `schema_version` + append-only `patient_record` snapshots make additive change cheap; removals would need a migration.

### 24. Alembic initial migration is an empty placeholder
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** ARCH-008
- **Ambiguous or undecided:** Phase 1 is a "navigable skeleton"; whether to hand-write full DDL now or defer to autogenerate.
- **Decision & rationale:** `backend/alembic/versions/0001_initial_schema.py` is an empty placeholder with a docstring specifying what the real Phase 2 migration must do (autogenerate from `app/db/models/`, enable RLS on `records.*` + `memory.patient_context`, add the audit UPDATE/DELETE-reject rule as defense in depth beyond the role GRANTs, wire the LangGraph checkpoint tables). `alembic/env.py` is fully wired to the models and app config. Avoids hand-maintaining DDL that will be regenerated.
- **Reversible?:** yes — `alembic revision --autogenerate` supersedes it in Phase 2.

### 25. Shipped `.env.example` defaults `EMBEDDING_BACKEND` / `RERANKER_BACKEND` to `stub`
- **Date / phase:** 2026-08-27 / Phase 1
- **Requirement ID(s):** PRD-106, PRD-G7, ARCH-004, ARCH-012
- **Ambiguous or undecided:** ARCHITECTURE.md §20 lists `EMBEDDING_BACKEND` default `local`. A fresh `docker compose up` / `make test` with `local` would require downloading model weights (network + GPU/CPU heavy), breaking "core flows work offline".
- **Decision & rationale:** The **committed `.env.example`** ships `stub` for both backends so a fresh checkout runs fully offline (deterministic pseudo-embeddings / lexical rerank via `app.llm.stub`). `local` and `gateway` remain the intended non-dev backends. ARCHITECTURE.md §20 updated to read `stub (dev) / local | gateway` for these two rows. Config default in `app/config.py` also set to `stub` to match the shipped file.
- **Reversible?:** yes — one env var per backend.

---

## Phase 1 — Checkpoint 1 corrections (triggered by operator-supplied guideline PDFs)

> Entries #26–#30 arose from the operator replacing the generated synthetic
> `SYNTH-GL-*.md` fixtures with three real multi-page clinical guideline PDFs in
> `data/sample_guidelines/` (WHO recommendations on newborn health, May 2017,
> 26 pp; WHO recommendations for management of serious bacterial infections in
> infants aged 0–59 days, Dec 2024, 107 pp; Comprehensive Newborn Care
> Protocols, Ministry of Health Kenya, Nov 2022, 174 pp — text + tables +
> figures/algorithms). **These entries record the decisions as PROPOSED and are
> pending explicit Checkpoint 1 confirmation; a follow-up entry will confirm or
> revise each.** ARCHITECTURE.md / ARCHITECTURE-ESSENTIALS.md edits are drafted
> but not yet applied, per the "do not proceed until confirmed" instruction.

### 26. Default dev guideline corpus is operator-provided real PDFs, not generated synthetic docs
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-006, PRD-001, PRD-A2 (supersedes / narrows DEVIATIONS #22)
- **Ambiguous or undecided:** DEVIATIONS #22 made `fetch_sample_guidelines.py` *generate* three tiny synthetic Markdown "guidelines" by default. Those do not resemble how real clinical guidelines are structured (multi-page, GRADE recommendation sets, clinical pathways, dosing tables, algorithm figures), so ingestion/chunking/retrieval/citation work built on them would be tuned to an unrepresentative fixture.
- **Decision & rationale (PROPOSED):** `data/sample_guidelines/` holds **only the real corpus**. The script (renamed `prepare_sample_guidelines.py`, `make prepare-guidelines`; `fetch-guidelines` kept as an alias) no longer generates content by default: it scans for real guideline files, checks each has a `manifest.json` entry, and warns (does not invent) for any missing metadata. Generating the tiny synthetic set is now opt-in (`--allow-synthetic` / `GUIDELINES_ALLOW_SYNTHETIC=true`) and is a **CI-only offline fixture**; those files move to `backend/tests/fixtures/guidelines/`. With no real docs and no flag the script exits non-zero telling the operator to add guideline PDFs.
- **Reversible?:** yes — the synthetic generator remains available behind a flag; nothing about the data model changes.

### 27. Guideline document-format heterogeneity — chunking needs format profiles, not one recommendation model
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** ARCH-013 (§6), SCOPE-1.2 (§9.1), PRD-004
- **Ambiguous or undecided:** ARCHITECTURE.md §6 rule 1 and its Rationale assume every guideline is a set of numbered GRADE recommendation statements ("… is recommended. (Strong recommendation, moderate certainty)"). The provided corpus shows at least three distinct formats: **GRADE recommendation set** (WHO 2017/2024), **clinical protocol / care pathway** (Kenya MOH: numbered pathways, step lists, dosing tables, algorithm flowcharts — no GRADE statements), and **narrative/background**. "Atomic recommendation" is therefore publisher/format-dependent.
- **Decision & rationale (PROPOSED):** Introduce a per-document `format_profile ∈ {grade_recommendations, clinical_protocol, narrative}` (detected at ingest and/or set in the manifest). Each profile defines the atomic unit: `grade_recommendations` → recommendation statement + strength/certainty/population qualifiers (current rule 1); `clinical_protocol` → a numbered protocol step / pathway node + its sub-bullets + any dose/parameter table bound to that step, kept atomic (`chunk_type = protocol_step`); `narrative` → prose chunking only (rule 2). SCOPE-1.2 reported-content framing gains a protocol variant ("Protocol X, step N states…", "Per [source] pathway, the documented step is…") — still reported-content, never directive. §6 Rationale reworded to say the atomic unit is profile-dependent while keeping the safety argument.
- **Reversible?:** yes — additive: a new `chunk_type` value and a per-document enum; documents without a detected profile fall back to `narrative`.

### 28. Figures / algorithms / flowcharts — add a `figure` chunk type; OCR out of scope
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** ARCH-013 (§6), ARCH-015 (§8.3), ARCH self-critique §21a
- **Ambiguous or undecided:** §6 covered prose / recommendation / table / list / criteria but was silent on figures. The Kenya MOH protocol is algorithm/flowchart-heavy and a clinical-pathway flowchart is frequently the content a clinician needs; a citation landing "near" a figure with no figure handling would have wrong or empty support.
- **Decision & rationale (PROPOSED):** Add `chunk_type = figure`: one chunk per figure holding the caption, any text extractable from the image region as **vector text already in the PDF** (embedded text layer), the nearest heading, and a stored page + bounding-box reference so the citation view can show the figure crop. **OCR is out of scope for MVP** — a figure with no extractable text is retained for citation/`expand_context` but is embedded from its caption only, weighted down in dense retrieval, and flagged so the §8.3 grounding check treats a caption-only / no-text figure as **at most `weak` support** (never the sole support for a claim → forces `weak_support` queue or escalation). Low overall extractable-text ratio → low `parse_quality`, visible badge, admin review before the document's chunks become retrievable.
- **Reversible?:** yes — additive `chunk_type` value + one grounding rule.

### 29. Document ingest metadata is operator-supplied via a per-file manifest, never inferred from PDF metadata — new ARCH-038; add `document.licence`
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** ARCH-038 (NEW — proposed), ARCH §5.1, ARCH §4.1, PRD-004, PRD-A2
- **Ambiguous or undecided:** §5.1 step 1 says `publisher` / `version_label` / `effective_date` are "recorded" but never says from where. All three provided PDFs have **empty PDF metadata** (`/Title` is null); version/effective-date live in the filename / cover page only. There is also no place to record each document's licence, which PRD-A2 requires be checked.
- **Decision & rationale (PROPOSED):** New decision **ARCH-038** — `POST /ingest/documents` takes the file plus a metadata object (`title`, `publisher`, `external_ref`, `version_label`, `effective_date`, `licence`, `topic_tags`, optional `format_profile`, optional `language`); batch/bundled ingestion reads the same fields per file from a sidecar `data/sample_guidelines/manifest.json`. Metadata is **never auto-committed from PDF metadata**; a cover-page heuristic may only *suggest* values for the admin to confirm. Add a `licence` column to `corpus.document`. Repo ships `data/sample_guidelines/manifest.example.json` (tracked) and gitignores the real `manifest.json` (same pattern as `.env`).
- **Reversible?:** partially — the manifest ingestion path and the `licence` column are additive; removing them later would need a migration.

### 30. Synthetic patient-record generator clinical domain must match the ingested guideline corpus domain
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-006, PRD-A3, SCOPE-2.1, SCOPE-2.2, ARCH §15 (relates to DEVIATIONS #23)
- **Ambiguous or undecided:** ARCHITECTURE.md §5.2 / §15.1 implicitly assume the synthetic records and the guideline corpus are in the same clinical domain (§15.1 step 2: "a synthetic record whose fields satisfy a chosen guideline's applicability"). The provided corpus is **neonatal / newborn / young-infant**; the Phase-1 `generate_synthetic_records.py` produces **adult inpatient** records (COPD, atrial fibrillation, adult drug doses). SCOPE-2.1 (stage classification against extractable criteria), SCOPE-2.2 (missing-info vs guideline requirements), and the auto-question generator all require record ↔ guideline-criteria domain overlap, which currently does not exist.
- **Decision & rationale (PROPOSED):** The record **schema** (`app/schemas/record.py`) stays domain-agnostic in structure. Add a generator `--domain` / `RECORD_DOMAIN` profile selecting the domain-specific content library (problem list, medications + weight-based dose patterns, vitals reference ranges, care settings, staging vocabulary). Ship a `neonatal` profile as the **default**, matching the bundled corpus; keep `adult_inpatient` as a second profile. A short note is added to §5.2 / §15 stating the generator domain must correspond to the ingested corpus.
- **Reversible?:** yes — profile selection is a flag; the schema and existing adult content library are retained.

### 31. Checkpoint 1 confirmation of #26–#30 — Approach A, applied
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-006, PRD-001, PRD-004, PRD-A2, PRD-A3, ARCH-013, ARCH-038, SCOPE-1.2, SCOPE-2.1, SCOPE-2.2, ARCH §5.1/§5.2/§6/§8.3/§9.1/§15/§20/§21a
- **Ambiguous or undecided:** #26–#30 were logged as PROPOSED pending explicit operator confirmation at Checkpoint 1.
- **Decision & rationale (CONFIRMED):** Operator confirmed on 2026-09-01: **Approach A** (`RECORD_DOMAIN` default = `neonatal`, matching the bundled corpus; `adult_inpatient` retained as an option) and instructed "apply the doc updates and the prepare-guidelines rework". Applied: ARCHITECTURE.md §3 (new ARCH-038), §4.1 (`document.licence`, `document_version.format_profile`/`parse_quality`, `chunk.chunk_type` += `protocol_step`/`figure`, `chunk.figure_ref`), §5.1 (manifest-supplied metadata; OCR out of scope; `parse_quality` gate), §5.2 (`RECORD_DOMAIN`), §6 (rule 0 format profile, rule 1b `protocol_step`, rule 3b `figure`, reworded Rationale), §8.3 (figure-support cap, step 5), §9.1 SCOPE-1.2 (protocol framing variant), §15 (domain-match note), §20 (`SAMPLE_GUIDELINES_DIR`, `GUIDELINES_ALLOW_SYNTHETIC`, `INGEST_MIN_PARSE_QUALITY`, `RECORD_DOMAIN`), §21a; ARCHITECTURE-ESSENTIALS.md §2 + §12; SQLAlchemy models `app/db/models/corpus.py`; `scripts/prepare_sample_guidelines.py` (replaces `fetch_sample_guidelines.py`, kept as a shim) + `data/sample_guidelines/manifest.example.json`; `app/config.py`, `.env.example`, `Makefile`, `README.md`, `.gitignore`; `scripts/generate_synthetic_records.py` gains `--domain` with a `neonatal` content library (default) and the existing `adult_inpatient` library. The synthetic `SYNTH-GL-*.md` fixtures now live under `backend/tests/fixtures/guidelines/` (generated on demand) and were removed from `data/sample_guidelines/`.
- **Reversible?:** yes — all changes are additive or config-gated; `#26–#30` "Reversible?" notes still hold.

### 32. Patient-record schema bumped to 1.1.0 to support the neonatal domain
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-002, PRD-003, PRD-A3, SCOPE-2.1, SCOPE-2.2 (extends DEVIATIONS #23, #30, #31)
- **Ambiguous or undecided:** DEVIATIONS #23 fixed the record schema at 1.0.0 with adult inpatient fields. Approach A (#31) makes `neonatal` the default `RECORD_DOMAIN`, but a credible neonatal record needs **weight**, **gestational age**, and **day of life** — none of which existed in 1.0.0. DEVIATIONS #23 said field refinements "bump `SCHEMA_VERSION` and are logged as new deviations".
- **Decision & rationale:** `SCHEMA_VERSION → 1.1.0`. Added (all optional/nullable, so 1.0.0 records still validate): `Vitals.weight_g`, `Vitals.mean_bp_mmhg`, `Encounter.gestational_age_weeks`, `Encounter.birth_weight_g`, `Encounter.day_of_life`. `data/record_schema.json` updated to match. No field removed or renamed; no migration needed for the append-only `patient_record` snapshot table (payloads are JSON blobs tagged with their `schema_version`).
- **Reversible?:** yes — additive nullable fields; a consumer that ignores them behaves exactly as under 1.0.0.

---

## Phase 1 — Checkpoint 1 corrections (triggered by an operator-supplied de-identified newborn dataset)

> The operator added a real **de-identified, anonymised newborn dataset** at
> `data/sample_records/rag_dataset.csv` (54 MB; long/EAV format —
> `key, field_name, field_value, context`; **40,871 patients**, one assessment
> snapshot each; Kenya Newborn Unit, 2021; 32 source variables across 6
> contexts: demographics, encounter_details, vitals, history_examination,
> interventions, medication) and asked to ingest it instead of generating
> synthetic records, mapping its fields onto `app/schemas/record.py`.
> Entries #33–#36 are **PROPOSED — pending explicit Checkpoint 1 confirmation**;
> #37 is a protective change applied immediately. ARCHITECTURE.md body edits and
> all code/schema/script changes are drafted, **not yet applied**.

### 33. Introduce a `deidentified` patient-data class alongside `synthetic` — departs from constraint #1
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-C1, PRD-081, PRD-080, PRD-A3, ARCH §5.2, ARCH-039 (NEW — proposed)
- **Ambiguous or undecided:** Constraint #1 / PRD-081 say **all** development/test/demo data must be **synthetic**; DEVIATIONS #16/#21 added an ingestion heuristic that rejects any "real-looking" batch lacking the `synthetic-generator-v1` marker. The operator has now supplied a **real** dataset (de-identified/anonymised) and instructed that it be ingested and used in place of synthetic records. This is a genuine departure from constraint #1 that only the operator can authorise.
- **Decision & rationale (PROPOSED — CONFIRM):** Add a `data_class ∈ {synthetic, deidentified}` concept. `deidentified` data:
  - carries `dataset_provenance = "deidentified-anonymised"` and a **dataset id**;
  - is admitted only with an **operator attestation** — a tracked `DATASET.md` sidecar (source, collection period/site, de-identification method + standard, consent/ethics basis, licence, known residual identifiers) **and** an explicit `--attest-deidentified` flag on the loader / `attestation` field on the API;
  - is otherwise treated **exactly like PHI** everywhere downstream: envelope-encrypted at rest, field-level RBAC, RLS, purpose-of-use, full audit, never leaves the deployment, never used for training (PRD-080/082-089 unchanged);
  - the real-data rejection heuristic (DEVIATIONS #16/#21) is updated to *allow* a batch that declares `data_class = deidentified` **with** a valid attestation, and continues to hard-reject anything that is neither marked-synthetic nor attested-deidentified.
  ARCHITECTURE.md constraint framing (§17.1 / §5.2) and PRD-081 wording to be amended to "synthetic **or** operator-attested de-identified" on confirmation.
- **Reversible?:** partially — the `data_class` field and attestation gate are additive; removing the class would mean deleting any ingested de-identified data.

### 34. Ingest EAV/long CSV via a reusable pivot + an external field-mapping spec; reorganise `data/`
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-002, PRD-003, PRD-006, ARCH §5.2, ARCH-039 (NEW — proposed)
- **Ambiguous or undecided:** ARCHITECTURE.md §5.2 assumed record ingestion is one JSON/CSV row per patient against the Pydantic schema. The supplied dataset is **entity-attribute-value / long** (`key, field_name, field_value, context`) and its variable names do not match `record.py`. There was also no home in `data/` for a non-synthetic record dataset, and `data/` mixes concerns.
- **Decision & rationale (PROPOSED — CONFIRM):**
  - New `app/ingestion/eav.py` — deterministic long→wide pivot keyed on `key`, then apply a declarative **mapping spec** (`field_mapping.yaml`): per source field → `{target: "<record.py path>", transform: "<named transform>", context: "<source context>"}`, plus `list_targets` groups for repeated-field families (exam findings, interventions, medications). The same spec is the contract for **file** ingestion now and a **pull API** later (b).
  - New `app/ingestion/sources/` — `PatientDataSource` interface with `FileEavSource` (implemented) and `RestApiPullSource` (**stub**, Phase 2+: configurable endpoint + auth + incremental backfill by `key`/updated-since).
  - New script `scripts/ingest_deidentified_records.py` (`--csv --mapping --dataset-id --attest-deidentified --out --limit`).
  - **Folder reorg (proposed):**
    ```
    data/
      record_schema.json
      sample_guidelines/            (unchanged — the guideline corpus)
      patient_records/
        synthetic/                  (was data/synthetic_records/; generator output)
        deidentified/
          newborn_nbu_2021/
            rag_dataset.csv         (moved from data/sample_records/)
            DATASET.md              (operator-filled provenance/attestation)
            field_mapping.yaml      (the mapping spec for this dataset)
      eav_cache/  eval_snapshots/
    ```
    `data/sample_records/` retired. `.gitignore` extended so no dataset file (synthetic or de-identified) is ever committed; only `DATASET.md` + `field_mapping.yaml` + `.gitkeep` are tracked (#37).
- **Reversible?:** yes — the pivot + mapping spec + sources seam are additive; the folder move is a one-time relocation with `Makefile`/`README`/config path updates.

### 35. Record-schema additions (→ 1.2.0) for exam findings, interventions, capillary refill — plus a name-field CONFLICT
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-002, PRD-003, PRD-A3, SCOPE-2.1, SCOPE-2.2 (extends DEVIATIONS #23, #32)
- **Ambiguous or undecided:** The dataset carries structured clinical signs (10 boolean history/examination findings), supportive interventions (7 booleans), specific antimicrobials (5 booleans), and capillary refill (1–3 s) — none of which have a home in `record.py` v1.1.0. Operator instruction (d): additions/mappings only; **conflicts need confirmation**.
- **Decision & rationale (PROPOSED — CONFIRM):** `SCHEMA_VERSION → 1.2.0`, additions only (all optional/nullable):
  - `Vitals.capillary_refill_seconds: float | None`
  - new `ExamFinding {name: str, present: bool, recorded_at: datetime | None}` + `PatientRecord.examination_findings: list[ExamFinding] = []`
  - new `Intervention {name: str, active: bool = True, started_at: datetime | None}` + `PatientRecord.interventions: list[Intervention] = []`
  - the 5 named antimicrobials map onto the **existing** `medications: list[Medication]` (`name` = drug, `active` = boolean; dose/route/frequency null).
  **CONFLICT requiring confirmation:** `PatientRecord.given_name: str` and `family_name: str` are **required**; a de-identified dataset has no names. Recommended resolution: make both `str | None = None` (a name is genuinely not always present, and de-identified data by definition omits it). This changes existing field definitions, so it is held for operator confirmation. Alternatives: populate with `""`/`"REDACTED"` on ingest (keeps the schema, hides the fact that no name exists), or gate validation on `data_class`.
- **Reversible?:** additions — yes. Name-field change — yes (widening a type; existing callers unaffected), but it *is* a change to an existing field, hence the confirmation gate.

### 36. `admission_date_time` is a retained date identifier — handling pending
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-080, PRD-083, PRD-C1, PRD-C2
- **Ambiguous or undecided:** The dataset retains full admission timestamps (`2021-01-09 00:45:00`). Exact dates are a direct identifier under HIPAA Safe Harbor and equivalent frameworks, so the dataset is "de-identified" under some other basis (limited dataset / ethics approval) rather than Safe Harbor. The architecture already encrypts every record field at rest and audits access, but does not date-shift.
- **Decision & rationale (PROPOSED — CONFIRM):** Default proposal — **retain `admission_date_time` as-is**, mapped to `encounter.admitted_at`, protected by the same envelope encryption + RBAC + audit as all record fields (it is needed for `day_of_life` reconstruction, vitals timestamping, and ordering). Alternative if the operator prefers stricter de-identification: an ingest-time transform (`date_shift` per `key`, or generalise to month) declared in `field_mapping.yaml`. The operator's `DATASET.md` must state the de-identification basis so this choice is documented.
- **Reversible?:** yes — the transform is a mapping-spec option; re-ingest applies it.

### 37. `.gitignore` extended so real/de-identified patient datasets are never committed — APPLIED NOW
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-C1, PRD-C2, PRD-080
- **Ambiguous or undecided:** `data/sample_records/rag_dataset.csv` (54 MB of real de-identified patient data) was **not** covered by any `.gitignore` rule and would have been committed on the next `git add -A`.
- **Decision & rationale (APPLIED):** Added `data/sample_records/*` and `data/patient_records/**` to `.gitignore`, tracking only `.gitkeep`, `DATASET.md`, and `field_mapping.yaml`. Applied immediately as a protective measure (not deferred to confirmation): committing real patient data — even de-identified — is not acceptable. No other change was made pending confirmation.
- **Reversible?:** trivially (it is a `.gitignore` line), but there is no reason to.

### 38. Checkpoint 1 confirmation of #33–#37 — C1/C2/C3 confirmed, applied
- **Date / phase:** 2026-09-01 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-002, PRD-003, PRD-006, PRD-080, PRD-081, PRD-C1, PRD-A3, ARCH-039, ARCH §4.2/§5.2/§17.1/§20, SCOPE-2.1, SCOPE-2.2
- **Ambiguous or undecided:** #33–#36 were logged as PROPOSED pending operator confirmation of three points (C1 real de-identified data class; C2 required name fields; C3 admission-datetime handling).
- **Decision & rationale (CONFIRMED & APPLIED):** Operator confirmed 2026-09-01: **C1** — add `data_class ∈ {synthetic, deidentified}` with an attestation gate, de-identified data handled exactly as PHI; **C2** — `PatientRecord.given_name`/`family_name` widened to `str | None = None`; **C3** — `admission_date_time` retained as-is (encrypted) mapped to `encounter.admitted_at`. Then instructed "apply the mapping + scripts + folder reorg". Applied:
  - **Schema v1.2.0** (`app/schemas/record.py`, `data/record_schema.json`): `Vitals.capillary_refill_seconds`; new `ExamFinding` + `examination_findings[]`; new `Intervention` + `interventions[]`; `given_name`/`family_name` optional; new `DEIDENTIFIED_PROVENANCE`. `required` in the JSON schema reduced to `[record_id, mrn]`.
  - **`app/schemas/enums.py`**: `DataClass{SYNTHETIC, DEIDENTIFIED}`.
  - **`app/ingestion/eav.py`**: long→wide pivot (`load_wide`), `MappingSpec.from_yaml`, transform registry (`identity/to_int/to_float/kg_to_g/sex_norm/bool_truthy/parse_datetime/none_literal_to_null`), `apply_mapping` (dotted paths incl. `vitals.0.x`, `list_targets`, `derived`, `defaults`), `build_records`.
  - **`app/ingestion/sources/`**: `PatientDataSource` (base), `FileEavSource` (implemented), `RestApiPullSource` (stub — pull-API seam, PRD-003).
  - **`app/ingestion/records.py`**: `DataClass`-aware `guard_batch` + `DatasetAttestation` (9 required fields) + `MissingAttestationError`; `looks_like_real_data`/`ingest_records` updated.
  - **`app/db/models/records.py`**: `patient.data_class`, `patient_record.dataset_id`; `source` allows `eav_file`.
  - **`scripts/ingest_deidentified_records.py`** (new) — refuses without `--attest-deidentified` and a complete `DATASET.md` front-matter attestation. **`app/api/routes/ingest.py`**: `POST /ingest/records/eav` stub.
  - **Folder reorg (DEVIATIONS #34):** `data/synthetic_records/` → `data/patient_records/synthetic/`; `data/sample_records/rag_dataset.csv` → `data/patient_records/deidentified/newborn_nbu_2021/rag_dataset.csv` (+ tracked `DATASET.md` template + `field_mapping.yaml`); `data/eav_cache/` added; `data/sample_records/` retired. `.gitignore` reworked so **no** dataset file is committable (only sidecars). `data/sample_records/` `.gitignore` lines replaced by `data/patient_records/**`.
  - **Config/docs:** `PATIENT_RECORDS_DIR`, `DEIDENTIFIED_ATTESTATION_REQUIRED` in `app/config.py` + `.env.example`; `Makefile` `ingest-deid` target + `gen-data` out-path; `pyproject.toml` adds `pyyaml`; ARCHITECTURE.md §3 (ARCH-039) / §4.2 / §5.2 (rewrite) / §17.1 / §20; ARCHITECTURE-ESSENTIALS.md §0/§11/§12; PRD.md constraint #1 preamble + PRD-081 + PRD-C1 + PRD-A3; CLAUDE.md §3 rule 1.
  - **Tests:** `test_eav_mapping.py` (pivot/transforms/list families/real dataset — skipped in CI), `test_ingest_deidentified.py` (attestation gate). 71 passing.
- **Reversible?:** additions and config gates are reversible; the folder move and the name-field widening are one-way but low-risk (widening a type; a relocation with path updates). `#33–#37` "Reversible?" notes still hold.

### 39. `Medication`/`Intervention` gain `stopped_at`; record-schema design principles stated → schema v1.3.0
- **Date / phase:** 2026-09-02 / Phase 1 (Checkpoint 1)
- **Requirement ID(s):** PRD-002, PRD-003, PRD-A3, ARCH-039, ARCH §4.2 (new "Record schema — design notes"), ARCH §5.2, SCOPE-2.1, SCOPE-2.2 (extends DEVIATIONS #23, #32, #35)
- **Ambiguous or undecided:** `Medication` and `Intervention` had `started_at` but no interval end, so a medication that stops mid-encounter (or is captured by a future longitudinal API) could not be represented. Operator also asked (b) that `record.py` stay small and API-ingestible — but there was **no stated design principle** in ARCHITECTURE.md for what belongs in the schema vs. an adapter, or how temporal entities are modelled, so each addition (v1.1→v1.2→…) has been ad hoc.
- **Decision & rationale:**
  - **Schema v1.3.0** — added `Medication.stopped_at: datetime | None = None` and `Intervention.stopped_at: datetime | None = None` (interval end; null = ongoing/unknown). Additive/optional; older records validate. `data/record_schema.json` synced. (Operator's example spelled it `stoped_at`; used the correct `stopped_at`, pairing with `started_at`.)
  - **Design principles written into ARCHITECTURE.md §4.2** ("Record schema — design notes") and ARCHITECTURE-ESSENTIALS.md §1a: one canonical `PatientRecord`, flat + **source-agnostic** (all source quirks live in the mapping spec / `PatientDataSource` adapter); **temporal entities** (`Medication`, `Intervention`) use a `started_at`/`stopped_at` pair, **point-in-time entities** (`Vitals`, `LabResult`, `ExamFinding`) use one `*_at`; repeated data is `list[TypedSubModel]`; evolution is additive-only, gated by `schema_version` (an API client on an older version still validates). This is the answer to (b) — it keeps `record.py` small and makes future REST-API ingestion a matter of writing another mapping spec, not extending the schema.
  - **Mapping** — the `newborn_nbu_2021` `field_mapping.yaml` already sets each medication's/intervention's `started_at` from `admission_date_time`, i.e. **equal to `encounter.admitted_at`** for every record (this dataset has no per-item start time; `stopped_at` has no source and stays null). Made explicit in the YAML comments and asserted in `tests/test_eav_mapping.py` (`test_medication_and_intervention_started_at_equals_admitted_at`, plus a real-dataset check). `field_mapping.yaml` + the TINY test mapping bumped to `schema_version: "1.3.0"`.
  - Two `test_ingest_deidentified.py` tests were reworked because the operator has now **completed** the `DATASET.md` attestation (it is no longer `TODO_CONFIRM`): the "front-matter lists all fields" test is now a structural check, and the "refuses incomplete attestation" test builds an incomplete attestation in a tmp dir; a new skip-if-absent test confirms a **complete** attestation + `--attest-deidentified` ingests 25 records successfully.
- **Reversible?:** yes — `stopped_at` is an additive nullable field; the design-principles text is documentation. Note: dataset provenance per the completed `DATASET.md` is the **Clinical Information Network (CIN)**, newborn units, 2021–2024 (earlier entries #33/#34 said "Kenya Newborn Unit, 2021" before the attestation was filled — not edited here, append-only).
