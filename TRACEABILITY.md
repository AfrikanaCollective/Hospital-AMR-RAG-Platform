# TRACEABILITY.md — Requirement → Implementation → Test → Status

Maps every requirement ID from [PRD.md](PRD.md) and [ARCHITECTURE.md](ARCHITECTURE.md)
to the file(s)/module(s) implementing it, its test(s), and its status.

**Status values:** `not started` · `in progress` · `done` · `deferred`
(a `deferred` row must carry a reason).

**Keep this current:** any time work begins or completes on a requirement,
update its row (status + implementing file(s) + test(s)) in the *same* change,
not as a follow-up. Treat an out-of-date row as a defect.

**Populated:** 2026-08-27 (Phase 0). **Updated:** 2026-08-27 (end of Phase 1).
Rows marked `in progress` have a scaffolded contract/interface **and a test**
in the Phase 1 skeleton; their behaviour is completed in the phase named in the
notes. Everything else is `not started`. Paths are relative to the repo root
(`backend/` omitted from `app/...` and `tests/...` for brevity — they live
under `backend/`).

Legend: `—` = not yet assigned.

---

## 1. Product requirements (PRD.md)

### 1.1 Ingestion & corpus

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-001 | Ingest external guideline documents (PDF) into a versioned corpus | `app/ingestion/pdf_parse.py`, `app/ingestion/tasks.py`, `app/api/routes/ingest.py` | — | not started |
| PRD-002 | Ingest patient records via flat file (CSV/JSON) | `app/ingestion/records.py`, `app/api/routes/ingest.py` | — | not started |
| PRD-003 | Ingest patient records via API | `app/ingestion/records.py`, `app/api/routes/ingest.py` | — | not started |
| PRD-004 | Chunks retain doc id + version + section path + page + char offset | `app/ingestion/chunking.py`, `app/db/models/corpus.py` | — | not started |
| PRD-005 | New guideline version supersedes without deleting; old citations resolve | `app/db/models/corpus.py` (`document_version.status`) | — | not started |
| PRD-006 | Synthetic patient-record generator + sample guideline documents | `scripts/generate_synthetic_records.py`, `scripts/fetch_sample_guidelines.py` | `tests/test_synthetic_generator.py` | in progress (Phase 1 — generator + offline guideline docs working; ingestion Phase 2) |

### 1.2 Retrieval, citation & grounding

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-010 | Hybrid retrieval: dense + BM25 + reranking | `app/retrieval/hybrid.py`, `app/retrieval/rerank.py`, `app/retrieval/vectorstore.py` | — | not started |
| PRD-011 | Every claim segment carries a citation (doc id + version + section/page + chunk offset) | `app/schemas/citation.py`, `app/citations/model.py`, `app/schemas/query.py` | `tests/test_citation_model.py` | in progress (Phase 1 — citation object + re-verification; emission Phase 3) |
| PRD-012 | Grounding check on every answer; unsupported segments flagged/removed/escalated | `app/grounding/verifier.py`, `app/grounding/segments.py` | — | not started |
| PRD-013 | Low-confidence retrieval → no general-knowledge answer; escalate or "not found" | `app/retrieval/confidence.py` | — | not started |
| PRD-014 | Conflicting sources → escalate, surface both with citations | `app/retrieval/conflict.py` | — | not started |
| PRD-015 | No relevant guideline → explicit "no guideline found", no recommendation | `app/retrieval/confidence.py`, `app/agents/guideline_synthesis_agent.py` | — | not started |
| PRD-016 | Citations machine-verifiable against stored chunk text/offsets | `app/citations/model.py` (`verify_citation`) | `tests/test_citation_model.py` | in progress (Phase 1 — verifier implemented) |

### 1.3 Multi-agent orchestration, memory & tools

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-020 | Multi-agent orchestration layer (LangGraph) with tool use | `app/agents/graph.py`, `app/agents/state.py`, `app/agents/*_agent.py` | `tests/test_smoke.py` | in progress (Phase 1 — topology + state defined; graph build Phase 3) |
| PRD-021 | Each agent bounded tool set + data scope; only patient-record agent has PHI access | `app/agents/registry.py` | `tests/test_agent_registry.py` | in progress (Phase 1 — allow-list enforcement + tests; agents Phase 3) |
| PRD-022 | Persistent memory: session conversation / per-patient context / reviewer history | `app/memory/*.py`, `app/db/models/memory.py` | — | not started |
| PRD-023 | Long agent runs checkpointed, resumable/inspectable | `app/memory/checkpointer.py`, `app/db/models/memory.py` | — | not started |
| PRD-024 | Recommendation-shaped memory writes rejected; no cross-patient blending | `app/memory/patient_context.py` (`validate_patient_context_write`) | `tests/test_patient_context_rejects_recommendations.py` | in progress (Phase 1 — validator + tests; persistence Phase 3) |

### 1.4 Human-in-the-loop

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-030 | HITL escalation with defined triggers | `app/schemas/enums.py` (`EscalationTrigger`), `app/hitl/triggers.py`, `app/hitl/escalation.py` | `tests/test_scope_boundary.py` | in progress (Phase 1 — trigger enum + release policy; flow Phase 3) |
| PRD-031 | HITL rank mode (structured multi-domain rubric) | `app/schemas/rubric.py`, `app/rubric/domains.py`, `app/api/routes/rubric.py`, `frontend/src/components/RubricForm.tsx` | `tests/test_rubric.py` | in progress (Phase 1 — rubric shape + form shell; capture Phase 3) |
| PRD-032 | HITL accept axis: full/partial/reject with defined state effects | `app/hitl/decisions.py` (`EFFECTS`), `app/schemas/hitl.py`, `frontend/src/components/AcceptAxisControls.tsx` | — | in progress (Phase 1 — effects contract + validation + UI shell; apply Phase 3) |
| PRD-033 | Every HITL action writes immutable audit + updates queue state | `app/hitl/decisions.py`, `app/audit/log.py` | — | not started |

### 1.5 Structured multi-rater evaluation

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-040 | 11-domain rubric, 5-pt Likert (incl. accuracy/safety/contextual/clarity) | `app/rubric/domains.py`, `app/schemas/rubric.py`, `app/db/models/eval.py` (`RubricDomain`) | `tests/test_rubric.py` | in progress (Phase 1 — 11 domains + anchors defined + asserted) |
| PRD-041 | Rubric scores stored as structured data (domain/score/rater/ts/result) | `app/db/models/eval.py` (`RubricRating`) | — | not started |
| PRD-042 | Workflow: rate → open queue → ≥3 distinct raters → IRR per domain → archive | `app/rubric/workflow.py`, `app/db/models/eval.py`, `app/rubric/tasks.py` | `tests/test_rubric.py` | in progress (Phase 1 — state machine + guard predicates; persistence Phase 3) |
| PRD-043 | "Distinct clinician" enforced (no self / no duplicate-account double count) | `app/rubric/workflow.py` (`is_eligible_rater`), `app/db/models/eval.py` (`RatingRound` UNIQUE) | `tests/test_rubric.py` | in progress (Phase 1 — predicate + DB constraint; dup-account detect Phase 3) |
| PRD-044 | IRR is a single named ordinal multi-rater metric (justified) | `app/rubric/irr.py`, `app/db/models/eval.py` (`IRRScore`, `IRRBatch`) | — | not started (Phase 3 — Krippendorff's alpha ordinal) |
| PRD-045 | Provenance tag `auto_generated`/`clinician_submitted`, visible throughout | `app/schemas/enums.py` (`Provenance`), `app/db/models/eval.py` (`eval_question.provenance`, `result.provenance`) | — | in progress (Phase 1 — enum + fields on models) |
| PRD-046 | Auto vs clinician results separately analysable, not pooled by default | `app/db/models/eval.py` (`IRRBatch.slice_definition`), `app/eval/harness.py` | — | not started |
| PRD-047 | Hard/adversarial cases included in the review queue | `app/rubric/workflow.py`, `app/api/routes/review_queue.py` | — | not started |
| PRD-048 | Purpose/limits statement: in-scope conformity evidence only | `app/rubric/__init__.py` (docstring), CDS-FUTURE.md | — | not started |

### 1.6 Capability scope

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-050 | In scope: grounded guideline reporting/synthesis for hypotheticals | `app/agents/guideline_synthesis_agent.py`, `app/agents/prompts/guideline_synthesis.md` | — | not started |
| PRD-051 | In scope: patient stage-of-care classification (grounded, cited, non-directive) | `app/agents/stage_classifier_agent.py`, `app/agents/prompts/stage_classifier.md` | — | not started |
| PRD-052 | In scope: missing-information identification (non-directive) | `app/agents/missing_info_agent.py`, `app/agents/prompts/missing_info.md` | — | not started |
| PRD-053 | Out of scope: autonomous next-step recommendation (walled off, not implemented) | `app/agents/next_step_recommender.py` (interface stub, no logic) | `tests/test_scope_boundary.py` | in progress (Phase 1 — stub asserted logic-free; enforcement Phase 3) |
| PRD-054 | Out of scope: guideline adjustment for local constraints (walled off, not implemented) | `app/agents/local_adaptation_agent.py` (stub → `capability_not_enabled`) | `tests/test_scope_boundary.py` | in progress (Phase 1 — stub asserted logic-free) |
| PRD-055 | Narrow exception: surface a documented alternative already in retrieved text | `app/scope/classifier.py`, `app/agents/guideline_synthesis_agent.py` | — | not started |
| PRD-056 | Extension seam (named unimplemented agent / interface stub) | `app/agents/local_adaptation_agent.py`, `app/agents/next_step_recommender.py`, `app/agents/graph.py`, `app/config.py` (`local_adaptation_enabled`) | `tests/test_scope_boundary.py`, `tests/test_smoke.py` | in progress (Phase 1 — seam in place, inert flag) |

### 1.7 Auto-generated hypothetical question set

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-060 | Auto-generated hypothetical question utility (record → narrative) | `app/eval/question_gen/generate.py`, `app/eval/question_gen/planner.py` | — | not started |
| PRD-061 | Narrative generation follows the no-fabrication discipline | `app/eval/question_gen/validate.py` | — | not started |
| PRD-062 | Generated questions diverse across guideline topics/sections | `app/eval/question_gen/generate.py` (dedup), `app/eval/question_gen/planner.py` | — | not started |
| PRD-063 | Expected-outcome label (`well_supported`/`missing_info_expected`/`no_guideline_expected`) | `app/schemas/enums.py` (`ExpectedOutcome`), `app/db/models/eval.py` (`eval_question.expected_outcome`) | `tests/test_question_gen_composition.py` | in progress (Phase 1 — enum + field, separate from provenance) |
| PRD-064 | Deliberate hard cases: sparse records + corpus gaps | `scripts/generate_synthetic_records.py` (sparse fraction), `app/eval/question_gen/generate.py` | `tests/test_synthetic_generator.py` | in progress (Phase 1 — sparse-record generation; corpus-gap cases Phase 2) |
| PRD-065 | 60/20/20 composition; hard cases ≤ 50% — documented decision | `app/eval/question_gen/planner.py` (`Composition`) | `tests/test_question_gen_composition.py` | in progress (Phase 1 — planner enforces split + cap) |
| PRD-066 | Auto Q/A used for fixed test set + queue seeding, kept separable | `app/db/models/eval.py` (`eval_question.in_fixed_testset`, provenance) | — | not started |

### 1.8 Evaluation harness

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-070 | Eval harness: retrieval precision/recall + citation accuracy vs a fixed synthetic set | `app/eval/harness.py`, `app/eval/metrics.py`, `app/eval/run.py` | — | not started |
| PRD-071 | Harness scores pass/fail vs the expected-outcome label | `app/eval/metrics.py` (`expected_outcome_pass`) | — | not started |
| PRD-072 | Harness runs reproducible: pinned corpus snapshot + config | `app/db/models/corpus.py` (`CorpusSnapshot`), `app/db/models/eval.py` (`EvalRun.config_snapshot`) | — | not started |
| PRD-073 | Harness reports by expected-outcome type and auto vs clinician subsets | `app/schemas/eval.py` (`EvalRunReport.by_provenance`), `app/eval/harness.py` | — | not started |

### 1.9 Security, privacy & safety

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-080 | All patient-record fields PHI by default, all environments | `app/schemas/record.py`, `app/db/models/records.py` | — | not started |
| PRD-081 | No real PHI ingested/accepted; synthetic only | `app/ingestion/records.py` (`looks_like_real_data`), `scripts/generate_synthetic_records.py` | `tests/test_synthetic_generator.py` | in progress (Phase 1 — synthetic marker + trust path; heuristic Phase 2) |
| PRD-082 | Encryption in transit for all communication | `deploy/nginx/nginx.conf`, `docker-compose.yml` | — | not started |
| PRD-083 | Encryption at rest for PHI incl. backups + free-text fields | `app/crypto/provider.py`, `app/db/models/*` (`*_enc` columns) | — | not started |
| PRD-084 | Field-level access control at API + data layer | `app/auth/rbac.py`, `app/db/models/records.py` (`RecordFieldPolicy`), `app/api/routes/records.py` | — | not started |
| PRD-085 | Immutable audit logging (who/what/when/chunks/model/response) | `deploy/postgres/init/01_schemas_roles.sql`, `app/db/models/audit.py`, `app/audit/log.py` | `tests/test_audit_append_only.py` | in progress (Phase 1 — schema + role grants + hash-chain helper; writer Phase 4) |
| PRD-086 | RBAC: clinician, reviewer, admin (+ service) | `app/auth/provider.py`, `app/auth/rbac.py`, `app/api/deps.py`, `app/db/models/iam.py` | — | in progress (Phase 1 — role model + route guards shell; enforcement Phase 4) |
| PRD-087 | Disclaimer layer, non-removable; agents defer to the human clinician | `app/schemas/query.py` (`DISCLAIMER_TEXT`, non-removable field), `frontend/src/components/DisclaimerBanner.tsx`, `app/agents/prompts/*.md` | `tests/test_grounding_wording.py` | in progress (Phase 1 — disclaimer constant + UI + prompt rules; API enforcement Phase 4) |
| PRD-088 | No independent diagnostic/treatment content; output filter | `app/grounding/wording.py` | `tests/test_grounding_wording.py` | in progress (Phase 1 — directive-phrasing filter; full filter Phase 3) |
| PRD-089 | No training on PHI; no PHI to external services; no PHI telemetry | `app/llm/gateway.py`, `app/logging.py` (redaction) | — | not started |
| PRD-090 | Ingested document text treated as untrusted (prompt-injection hardening) | `app/agents/prompts/*.md`, `app/agents/__init__.py` (rules) | — | not started |

### 1.10 Platform, config & deployment

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-100 | Backend in Python (FastAPI) | `app/main.py`, `app/api/**` | `tests/test_smoke.py` | in progress (Phase 1 — app factory + router + route stubs) |
| PRD-101 | LLM model id from env/config w/ placeholder; flag unverifiable names | `app/config.py` (`validate_model_config`), `app/llm/gateway.py` | `tests/test_config_model_verification.py` | in progress (Phase 1 — config + startup check + no-literal test; calls Phase 2) |
| PRD-102 | Self-hosted LLM gateway with fallback routing | `app/llm/gateway.py` (`model_chain`), `app/llm/stub_server.py` | `tests/test_config_model_verification.py` | in progress (Phase 1 — chain + stub server; HTTP + routing Phase 2) |
| PRD-103 | Embedding + reranker model ids config-driven w/ placeholders | `app/config.py`, `app/ingestion/embed.py`, `app/retrieval/rerank.py` | — | in progress (Phase 1 — config surface + stub backends) |
| PRD-104 | One self-hosted vector store, justified | `app/retrieval/vectorstore.py` (Qdrant adapter), `docker-compose.yml` | — | in progress (Phase 1 — adapter interface + service) |
| PRD-105 | Redis + Celery for async ingestion + long agent tasks | `app/worker.py`, `app/ingestion/tasks.py`, `app/eval/tasks.py`, `app/rubric/tasks.py`, `docker-compose.yml` | — | in progress (Phase 1 — Celery app + task stubs + services) |
| PRD-106 | Docker/docker-compose; core flows work offline | `docker-compose.yml`, `Makefile`, `app/llm/stub*.py`, `.env.example` | — | in progress (Phase 1 — compose stack + offline stubs; full stack Phase 4) |
| PRD-107 | React frontend: query UI + citation display + 3 HITL modes | `frontend/src/**` | — | in progress (Phase 1 — UI shell for query, citations, rank + accept axis) |
| PRD-108 | Config via env/files; no hardcoded secrets; configurable secrets backend | `app/config.py`, `.env.example`, `app/crypto/provider.py` | — | in progress (Phase 1 — pydantic-settings + SECRETS_BACKEND; vault Phase 4) |

### 1.11 Non-functional requirements

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-NFR-1 | Soft latency target (~15 s p50) documented, not enforced | ARCHITECTURE.md §NFR | — | deferred (documented target only) |
| PRD-NFR-2 | Safe degradation: never an ungrounded answer on component failure | `app/grounding/verifier.py`, `app/agents/orchestrator.py`, `frontend/src/components/AnswerView.tsx` | — | not started |
| PRD-NFR-3 | Reproducibility: pinned deps + pinned eval config | `backend/pyproject.toml`, `app/db/models/corpus.py` (`CorpusSnapshot`) | — | not started (exact pins Phase 2) |
| PRD-NFR-4 | Observability: structured logs, basic metrics, propagated trace IDs | `app/logging.py`, `app/api/middleware.py` | — | in progress (Phase 1 — logging + request-id middleware shell) |
| PRD-NFR-5 | Data minimisation: least-privilege fields; record vectors off by default | `app/config.py` (`patient_record_vectors_enabled`), `app/agents/registry.py` | `tests/test_agent_registry.py` | in progress (Phase 1 — flag + allow-lists) |
| PRD-NFR-6 | Portability: single-host docker-compose, no managed cloud for core | `docker-compose.yml` | — | in progress (Phase 1) |

### 1.12 Build constraints

| ID | Constraint (short) | Enforced by | Test(s) | Status |
|---|---|---|---|---|
| PRD-C1 | No real PHI, ever — synthetic data only | `scripts/generate_synthetic_records.py`, `app/ingestion/records.py`, CLAUDE.md §3 | `tests/test_synthetic_generator.py` | in progress |
| PRD-C2 | PHI-aware architecture: encryption + field ACL + immutable audit are core | `app/crypto/**`, `app/auth/rbac.py`, `app/audit/**`, `deploy/postgres/init/**` | `tests/test_audit_append_only.py` | in progress |
| PRD-C3 | No diagnostic/treatment generation; disclaimer layer; defer to human | `app/grounding/wording.py`, `app/schemas/query.py`, `app/agents/prompts/**` | `tests/test_grounding_wording.py` | in progress |
| PRD-C4 | Grounding enforced, not assumed (citation format, grounding check, HITL triggers) | `app/citations/model.py`, `app/grounding/**`, `app/retrieval/confidence.py`, `app/hitl/triggers.py` | `tests/test_citation_model.py` | in progress |
| PRD-C5 | Production-grade patterns, minimal feature surface; no silent scope expansion | process (CLAUDE.md), DEVIATIONS.md | — | in progress (process) |
| PRD-C6 | Config not hardcoding for LLM (and embedding/reranker) model ids | `app/config.py`, `app/llm/gateway.py` | `tests/test_config_model_verification.py` | in progress |
| PRD-C7 | Phase checkpoints are hard stops | process (CLAUDE.md §2) | n/a | in progress |
| PRD-C8 | The CDS-FUTURE.md boundary is hard; stop and flag rather than work around | `app/agents/local_adaptation_agent.py`, `app/agents/next_step_recommender.py`, CLAUDE.md §3 | `tests/test_scope_boundary.py` | in progress |

### 1.13 Goals / success criteria

| ID | Goal (short) | Measured by | Test(s) | Status |
|---|---|---|---|---|
| PRD-G1 | ≥95% citations resolve + support the adjacent claim (eval set) | `app/eval/metrics.py` | — | not started |
| PRD-G2 | 100% of `no_guideline_expected` cases return explicit "no guideline found" | `app/eval/metrics.py`, `app/eval/harness.py` | — | not started |
| PRD-G3 | ≥90% of `missing_info_expected` cases request the missing field(s) | `app/eval/metrics.py` | — | not started |
| PRD-G4 | 0 outputs cross into excluded CDS capabilities | `app/eval/harness.py`, `tests/test_scope_boundary.py` | `tests/test_scope_boundary.py` | in progress (Phase 1 — contract tests; behavioural gating Phase 3) |
| PRD-G5 | 100% of retrievals + model responses produce an audit record | `app/audit/log.py` | — | not started |
| PRD-G6 | Rubric + multi-rater + IRR workflow runs end-to-end; auto vs clinician separate | `app/rubric/**`, `app/eval/**` | — | not started |
| PRD-G7 | `docker compose up` brings up the full stack offline for core flows | `docker-compose.yml`, `app/llm/stub_server.py` | — | in progress (Phase 1 — stubs enable offline; full verification Phase 4) |

---

## 2. Architectural decisions (ARCHITECTURE.md)

| ID | Decision (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| ARCH-001 | Backend: Python + FastAPI | `app/main.py`, `app/api/**` | `tests/test_smoke.py` | in progress |
| ARCH-002 | Vector store: Qdrant (justified vs Chroma) | `app/retrieval/vectorstore.py`, `docker-compose.yml` | — | in progress (adapter interface only) |
| ARCH-003 | Retrieval: dense + sparse BM25 + cross-encoder rerank, RRF fusion | `app/retrieval/hybrid.py`, `app/retrieval/rerank.py` | — | not started |
| ARCH-004 | Embedding model config-driven (placeholder, flagged) | `app/config.py`, `app/ingestion/embed.py` | `tests/test_config_model_verification.py` | in progress |
| ARCH-005 | `LLMGateway`: `MODEL_ID` + fallbacks from config; startup model-name verification | `app/config.py`, `app/llm/gateway.py` | `tests/test_config_model_verification.py` | in progress |
| ARCH-006 | Orchestration: LangGraph | `app/agents/graph.py`, `app/agents/state.py` | `tests/test_smoke.py` | in progress (topology + state) |
| ARCH-007 | Async: Redis + Celery | `app/worker.py`, `docker-compose.yml` | — | in progress |
| ARCH-008 | PostgreSQL single system of record (7 schemas) | `app/db/models/**`, `app/db/session.py`, `deploy/postgres/init/01_schemas_roles.sql`, `backend/alembic/**` | `tests/test_audit_append_only.py` | in progress (models + schemas + roles; migration Phase 2) |
| ARCH-009 | Deploy: Docker + docker-compose, offline core flows | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | — | in progress |
| ARCH-010 | Frontend: React (Vite + TS), static | `frontend/**` | — | in progress |
| ARCH-011 | Auth: OIDC-ready `AuthProvider`, dev-JWT for MVP; roles | `app/auth/**`, `app/db/models/iam.py` | — | in progress (interfaces + role model) |
| ARCH-012 | Reranker: config-driven cross-encoder (placeholder, flagged) | `app/config.py`, `app/retrieval/rerank.py` | — | in progress |
| ARCH-013 | Chunking: structure-aware, recommendation-atomic | `app/ingestion/chunking.py` | — | not started |
| ARCH-014 | Citation object schema (min: doc id + version + section/page + chunk offset + quote) | `app/schemas/citation.py`, `app/citations/model.py` | `tests/test_citation_model.py` | in progress |
| ARCH-015 | Grounding gate: citation-resolves / quote-integrity / entailment / scope-wording | `app/grounding/verifier.py`, `app/grounding/wording.py`, `app/citations/model.py` | `tests/test_grounding_wording.py`, `tests/test_citation_model.py` | in progress (deterministic parts scaffolded; entailment + verdict Phase 3) |
| ARCH-016 | Multi-agent topology (9 roles, LangGraph, per-node checkpoint, tool allow-lists) | `app/agents/graph.py`, `app/agents/registry.py`, `app/agents/*_agent.py` | `tests/test_agent_registry.py`, `tests/test_smoke.py` | in progress |
| ARCH-017 | Persistent memory stores (session conv / patient_context / rating history / checkpoints / hot state) | `app/memory/**`, `app/db/models/memory.py`, `app/db/models/eval.py` | — | in progress (models + validator) |
| ARCH-018 | HITL escalation trigger codes + lifecycle | `app/schemas/enums.py`, `app/hitl/triggers.py`, `app/hitl/escalation.py` | `tests/test_scope_boundary.py` | in progress (codes + release policy) |
| ARCH-019 | HITL interaction modes (rank axis + accept axis) and their effect on state | `app/hitl/decisions.py` (`EFFECTS`), `app/schemas/hitl.py`, `app/schemas/rubric.py` | — | in progress (effects contract + validation) |
| ARCH-020 | Multi-rater rubric workflow state machine + open queue + min-rater enforcement | `app/rubric/workflow.py`, `app/db/models/eval.py` | `tests/test_rubric.py` | in progress |
| ARCH-021 | IRR metric: Krippendorff's alpha (ordinal) per domain; secondary AC2/ICC | `app/rubric/irr.py` | — | not started (Phase 3) |
| ARCH-022 | Auto-generated hypothetical question set pipeline (60/20/20, validator, gold re-check) | `app/eval/question_gen/**` | `tests/test_question_gen_composition.py` | in progress (planner + composition guard) |
| ARCH-023 | Patient-record vectorization OFF by default; separate collection if enabled | `app/config.py` (`patient_record_vectors_enabled`), `app/retrieval/vectorstore.py` | — | in progress (flag) |
| ARCH-024 | `patient_context` repo rejects recommendation-shaped writes; no cross-patient reads | `app/memory/patient_context.py` | `tests/test_patient_context_rejects_recommendations.py` | in progress |
| ARCH-025 | Scope enforcement: scope-classifier routes SCOPE-2.3/2.4 to escalation; no composing tool | `app/scope/classifier.py`, `app/hitl/triggers.py` (`NEVER_ANSWERED`), `app/agents/registry.py` | `tests/test_scope_boundary.py` | in progress (marker lists + never-answered set; classifier Phase 3) |
| ARCH-026 | Extension seam: `local-adaptation` agent stub + reserved `next-step-recommender` + inert flag | `app/agents/local_adaptation_agent.py`, `app/agents/next_step_recommender.py`, `app/agents/graph.py`, `app/config.py` | `tests/test_scope_boundary.py`, `tests/test_smoke.py` | in progress |
| ARCH-030 | Evaluation harness design (retrieval P/R, citation accuracy, expected-outcome pass/fail, subset reporting) | `app/eval/harness.py`, `app/eval/metrics.py`, `app/schemas/eval.py` | — | not started |
| ARCH-031 | Encryption in transit (TLS at proxy, private net, authenticated services) | `deploy/nginx/nginx.conf`, `docker-compose.yml` | — | in progress (proxy + private net; TLS certs Phase 4) |
| ARCH-032 | Encryption at rest (host volume + app envelope encryption for enumerated PHI fields) | `app/crypto/provider.py`, `app/db/models/*` (`*_enc`) | — | in progress (interface + encrypted columns declared) |
| ARCH-033 | Key management (`SECRETS_BACKEND`, `CryptoProvider`, dev-key warning) | `app/crypto/provider.py`, `app/config.py` | — | in progress (interface + dev-key warning) |
| ARCH-034 | Access control (`AuthProvider`, RBAC + RLS + `record_field_policy` + per-agent tool allow-list + purpose-of-use) | `app/auth/**`, `app/api/deps.py`, `app/agents/registry.py`, `app/db/session.py` (RLS GUC), `app/db/models/records.py` | `tests/test_agent_registry.py` | in progress (tool allow-list enforced; RBAC/RLS Phase 4) |
| ARCH-035 | Audit logging (append-only grants, hash chain, encrypted text + hashes, one event per action) | `deploy/postgres/init/01_schemas_roles.sql`, `app/db/models/audit.py`, `app/audit/log.py` | `tests/test_audit_append_only.py` | in progress |
| ARCH-036 | Deployment architecture (compose services + profiles + non-root + healthchecks) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/**` | — | in progress |
| ARCH-037 | Safety/disclaimer layer (non-removable disclaimer field, prompt framing, output filter) | `app/schemas/query.py`, `app/grounding/wording.py`, `app/agents/prompts/**`, `frontend/src/components/DisclaimerBanner.tsx` | `tests/test_grounding_wording.py` | in progress |

*(ARCH-027, ARCH-028, ARCH-029 intentionally unused — IDs are permanent and need not be contiguous.)*

---

## 3. Capability-scoping items (ARCHITECTURE.md §9)

| ID | Item (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| SCOPE-1.1 | Hypothetical guideline-lookup → synthesized cited answer | `app/agents/guideline_synthesis_agent.py` | — | not started |
| SCOPE-1.2 | Reported-content framing enforced in every guideline-touching agent's prompt template + filter | `app/agents/prompts/*.md`, `app/grounding/wording.py` | `tests/test_grounding_wording.py` | in progress (prompt rules + directive filter) |
| SCOPE-1.3 | Explicit "no guideline found"; no general-knowledge fallback (incl. hypotheticals) | `app/retrieval/confidence.py`, `app/agents/guideline_synthesis_agent.py` | — | not started |
| SCOPE-1.4 | Auto-generated hypothetical question set is scope-1-framed | `app/eval/question_gen/generate.py`, `app/agents/prompts/orchestrator_scope.md` | — | not started |
| SCOPE-2.1 | Patient stage-of-care classification from extractable, cited criteria; escalate if uncertain | `app/agents/stage_classifier_agent.py` | — | not started |
| SCOPE-2.2 | Missing-information identification vs matched guideline requirements, each cited | `app/agents/missing_info_agent.py` | — | not started |
| SCOPE-2.3 | **EXCLUDED** — autonomous next-step recommendation from patient data; not implemented | `app/agents/next_step_recommender.py` (interface stub, no logic) | `tests/test_scope_boundary.py` | in progress (stub asserted logic-free) |
| SCOPE-2.4 | **EXCLUDED** — guideline adjustment for local operational constraints; not implemented | `app/agents/local_adaptation_agent.py` (stub → `capability_not_enabled`) | `tests/test_scope_boundary.py` | in progress (stub asserted logic-free) |
| SCOPE-2.5 | Narrow exception: surface a documented alternative already present in retrieved text; else escalate | `app/scope/classifier.py`, `app/agents/guideline_synthesis_agent.py`, `app/hitl/triggers.py` | — | not started |

---

## 4. Tracked decisions — not implementation requirements

Non-goals, assumptions, and open questions are tracked decisions but not things
to "build", so they are recorded here as `deferred` with a disposition rather
than `not started` (DEVIATIONS.md #19).

### 4.1 Non-goals (PRD.md §7)

| ID | Non-goal (short) | Disposition | Status |
|---|---|---|---|
| PRD-NG-001 | No diagnoses / treatment plans / independent recommendations | Enforced by SCOPE model + output filter + tests | deferred (by design) |
| PRD-NG-002 | No autonomous next-step recommendation from patient data | Enforced — SCOPE-2.3 exclusion + scope-classifier + `test_scope_boundary.py` | deferred (by design) |
| PRD-NG-003 | No guideline adjustment for local operational constraints | Enforced — SCOPE-2.4 exclusion + stub + `test_scope_boundary.py` | deferred (by design) |
| PRD-NG-004 | Does not replace clinician judgement / act as authority of record | Enforced by disclaimer layer | deferred (by design) |
| PRD-NG-005 | No Android / native mobile app in MVP | Not built; revisit only on request after Phase 5 | deferred (by design) |
| PRD-NG-006 | No EHR write-back, order entry, or actions on hospital systems | Read-only w.r.t. patient data; no such endpoints | deferred (by design) |
| PRD-NG-007 | No multi-tenant / multi-hospital SaaS | Single deployment; no tenancy model | deferred (by design) |
| PRD-NG-008 | Not a general-purpose medical chatbot | Enforced by grounding + "no guideline found" | deferred (by design) |
| PRD-NG-009 | No model training / fine-tuning (certainly not on PHI) | No training code path | deferred (by design) |
| PRD-NG-010 | Rubric/IRR evidence is not regulatory clearance | Stated in-product + reports (PRD-048) | deferred (by design) |
| PRD-NG-011 | No cohort / cross-patient analytics; one patient per session | Enforced by conversation model + orchestrator | deferred (by design) |
| PRD-NG-012 | No real-time streaming ingestion / HL7 / FHIR feed | File + simple API ingestion only | deferred (by design) |

### 4.2 Assumptions (PRD.md §8)

| ID | Assumption (short) | Status |
|---|---|---|
| PRD-A1 | Self-hosted LLM gateway available/stubbed; model catalogue via config | deferred (assumption) |
| PRD-A2 | Sample public guideline PDFs obtainable for dev; licences permit local use | deferred (assumption) |
| PRD-A3 | Patient-record schema stable enough to fix in Phase 1; synthetic mirrors it | deferred (assumption — v1.0.0 fixed in `app/schemas/record.py`; refinable, DEVIATIONS #23) |
| PRD-A4 | Enough reviewers to reach 3-distinct-rater minimum for a sample; else auto-seed | deferred (assumption) |
| PRD-A5 | Reference deployment is a single host (GPU or CPU fallback) | deferred (assumption) |
| PRD-A6 | Regulatory classification / clinical governance / validation are out of engineering scope | deferred (assumption) |

### 4.3 Open questions (PRD.md §9 / ARCHITECTURE.md §22)

| ID | Question (short) | Status |
|---|---|---|
| PRD-Q1 | Guideline version authority when two versions are retrievable | deferred (open question) |
| PRD-Q2 | Reviewer SLA / after-hours behaviour (interim: hold + safe message) | deferred (open question) |
| PRD-Q3 | Retention periods for audit / patient_context / rubric data | deferred (open question) |
| PRD-Q4 | Whether reviewer partial-accept edits feed any future example set (drift risk) | deferred (open question) |
| PRD-Q5 | Minimum corpus coverage before a clinical area is "usable" | deferred (open question) |

---

## Summary counts (2026-08-27, end of Phase 1)

- Implementation requirements tracked: **PRD 0xx–1xx (66)** + **PRD-NFR (6)** +
  **PRD-C (8)** + **PRD-G (7)** + **ARCH (34)** + **SCOPE (9)** = **130**
- Status: `in progress` ~70 (scaffolded contract + test) · `not started` ~59 ·
  `deferred` 1 (PRD-NFR-1) · `done` 0
- Tracked decisions (non-goals / assumptions / open questions): **23**, all `deferred`
- Backend test suite: **49 passing**, offline (no DB / network / real models)
