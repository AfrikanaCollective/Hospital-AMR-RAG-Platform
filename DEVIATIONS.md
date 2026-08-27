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
