# TRACEABILITY.md — Requirement → Implementation → Test → Status

Maps every requirement ID from [PRD.md](PRD.md) and [ARCHITECTURE.md](ARCHITECTURE.md)
to the file(s)/module(s) implementing it, its test(s), and its status.

**Status values:** `not started` · `in progress` · `done` · `deferred`
(a `deferred` row must carry a reason).

**Keep this current:** any time work begins or completes on a requirement,
update its row (status + implementing file(s) + test(s)) in the *same* change,
not as a follow-up. Treat an out-of-date row as a defect.

**Populated:** 2026-08-27 (Phase 0). **Updated:** 2026-08-27 (end of Phase 1);
2026-09-01 / 2026-09-02 (Checkpoint 1 — all **applied**): guideline-PDF
corrections (DEVIATIONS #26–#32); the operator de-identified-newborn-dataset
changes, C1/C2/C3 confirmed (DEVIATIONS #33–#38); record-schema temporal fields
+ design principles → schema v1.3.0 (DEVIATIONS #39).
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
| PRD-001 | Ingest external guideline documents (PDF) into a versioned corpus | `app/ingestion/pdf_parse.py`, `app/ingestion/chunking.py`, `app/ingestion/documents.py`, `app/ingestion/chunk_persistence.py`, `app/ingestion/tasks.py`, `app/api/routes/ingest.py`, `app/schemas/ingest.py`, `scripts/prepare_sample_guidelines.py`, `data/sample_guidelines/manifest.example.json` | `tests/test_prepare_guidelines.py`, `tests/test_pdf_parse.py`, `tests/test_chunking.py`, `tests/test_document_persistence.py`, `tests/test_chunk_persistence.py`, `tests/test_process_document_task.py`, `tests/test_ingest_routes.py` | in progress (Phase 2 — parse + chunk implemented and tested for `.pdf` and `.md` sources (DEVIATIONS #47); `document`/`document_version` creation + supersession (DEVIATIONS #59) and `corpus.chunk` persistence + Qdrant upsert implemented and verified against a real Postgres + Qdrant. `POST /ingest/documents` HTTP route implemented (multipart upload, manifest-shaped form fields, `409` on a same-name/different-content conflict, enqueues `process_document` on a genuinely new version) — DEVIATIONS #65) |
| PRD-002 | Ingest patient records via flat file (CSV/JSON + EAV/long) | `app/ingestion/eav.py`, `app/ingestion/sources/file_eav.py`, `app/ingestion/records.py` (`guard_batch`, `ingest_records`, `parse_wide_upload`), `scripts/ingest_deidentified_records.py` (`--persist`), `app/api/routes/ingest.py`, `app/schemas/ingest.py`, `app/schemas/record.py` (**v1.3.0**) | `tests/test_eav_mapping.py`, `tests/test_ingest_deidentified.py`, `tests/test_ingest_records_persistence.py`, `tests/test_parse_wide_upload.py`, `tests/test_ingest_routes.py` | in progress — **applied at Checkpoint 1 (C1/C2/C3 confirmed):** EAV pivot + declarative `field_mapping.yaml` + transform registry; schema **v1.3.0**. Phase 2: `ingest_records` persists `patient`/`patient_record` rows (dedupe on MRN via `patient.mrn_hash`, DEVIATIONS #57), wired into `scripts/ingest_deidentified_records.py --persist` and into the new `POST /ingest/records/file` (JSON full-fidelity / CSV scalar-only, DEVIATIONS #64) and `POST /ingest/records/eav` (reuses `FileEavSource`, `mapping_ref` resolution DEVIATIONS #65) HTTP routes — all verified (the CLI path against a real Postgres; the HTTP routes via FastAPI's TestClient with `get_db`/`current_principal` dependency-overridden, matching this scaffold's pre-Phase-4-auth testing pattern). |
| PRD-003 | Ingest patient records via API | `app/ingestion/sources/base.py` (`PatientDataSource`), `app/ingestion/sources/rest_api.py` (stub), `app/api/routes/ingest.py` (`POST /ingest/records`), `app/schemas/record.py` (`RecordIngestBatch`, design principles — ARCH §4.2) | `tests/test_eav_mapping.py`, `tests/test_ingest_routes.py` | in progress — **applied at Checkpoint 1:** `PatientDataSource` seam — `FileEavSource` implemented, `RestApiPullSource` stub reusing the same `field_mapping.yaml`. Phase 2: `POST /ingest/records` implemented — `RecordIngestBatch` request body, 500-record bound per call (`413` over), deidentified batches rejected (`RecordIngestBatch` carries no attestation field, DEVIATIONS #65) — tested via FastAPI's TestClient. |
| PRD-004 | Chunks retain doc id + version + section path + page + char offset | `app/ingestion/chunking.py`, `app/ingestion/chunk_persistence.py`, `app/ingestion/corpus_access.py`, `app/api/routes/corpus.py`, `app/db/models/corpus.py` | `tests/test_chunking.py`, `tests/test_chunk_persistence.py`, `tests/test_corpus_access.py`, `tests/test_corpus_routes.py` | in progress (Phase 2 — `chunk_document` emits the full span per chunk; `persist_chunks` writes `corpus.chunk` rows resolving `parent_ordinal` -> real `parent_chunk_id`, verified against a real Postgres. Phase 4: `GET /corpus/chunks/{chunk_id}` implemented) |
| PRD-005 | New guideline version supersedes without deleting; old citations resolve | `app/db/models/corpus.py` (`document_version.status`), `app/ingestion/corpus_access.py` (`withdraw_version`), `app/api/routes/corpus.py` | `tests/test_corpus_access.py`, `tests/test_corpus_routes.py` | in progress (Phase 4: `GET /corpus/documents`, `GET /corpus/documents/{id}/versions`, `POST /corpus/versions/{id}/withdraw` implemented — withdrawal is a status change only, never a delete; a withdrawn version's chunks still resolve, verified against a real ephemeral Postgres, DEVIATIONS #90) |
| PRD-006 | Dev data: synthetic record generator (fallback) + guideline corpus + an operator-supplied **de-identified newborn dataset** (default record source) | `scripts/generate_synthetic_records.py` (`--domain`), `scripts/prepare_sample_guidelines.py`, `scripts/ingest_deidentified_records.py`, `data/patient_records/deidentified/newborn_nbu_2021/{DATASET.md,field_mapping.yaml}`, `data/sample_guidelines/manifest.example.json` | `tests/test_synthetic_generator.py`, `tests/test_prepare_guidelines.py`, `tests/test_eav_mapping.py`, `tests/test_ingest_deidentified.py` | in progress — **corrected + applied at Checkpoint 1** (DEVIATIONS #26–#39): guidelines = operator PDFs + manifest; records = de-identified `newborn_nbu_2021` (CIN, 2021–2024; EAV → `record.py` v1.3.0 via `field_mapping.yaml`, attestation now completed by the operator). Synthetic generator is the fallback. Persist-to-DB is Phase 2. |

### 1.2 Retrieval, citation & grounding

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-010 | Hybrid retrieval: dense + BM25 + reranking | `app/retrieval/hybrid.py`, `app/retrieval/rerank.py`, `app/retrieval/vectorstore.py` | `tests/test_hybrid_retrieve.py` | in progress (Phase 2 — `retrieve()` implemented: query construction, Qdrant dense+sparse search, server-side RRF fusion, rerank, confidence, conflict detection, retrieval snapshot; tested against qdrant-client's embedded `:memory:` mode with stub embed/rerank backends. Context expansion (`expand_context`) is a Phase-3 agent tool, not run here) |
| PRD-011 | Every claim segment carries a citation (doc id + version + section/page + chunk offset) | `app/schemas/citation.py`, `app/citations/model.py`, `app/schemas/query.py` | `tests/test_citation_model.py`, `tests/test_build_citation.py` | in progress (Phase 1 — citation object + re-verification; Phase 2 — `build_citation` pulled forward, DEVIATIONS #46, no agent dependency; segmentation into claim/framing segments to attach citations to remains Phase 3) |
| PRD-012 | Grounding check on every answer; unsupported segments flagged/removed/escalated | `app/grounding/verifier.py`, `app/grounding/segments.py` | — | not started — Phase 3 (needs the synthesis agent's claim segments as input) |
| PRD-013 | Low-confidence retrieval → no general-knowledge answer; escalate or "not found" | `app/retrieval/confidence.py` | — | in progress (Phase 1 — `assess()` implemented; wiring into `retrieve()`'s returned verdict is the remaining Phase 2 piece) |
| PRD-014 | Conflicting sources → escalate, surface both with citations | `app/retrieval/conflict.py` | `tests/test_conflict.py` | in progress (Phase 2 — `detect_conflicts` implemented: same-section/different-active-version text divergence + lexical negation heuristic between recommendation chunks, DEVIATIONS #53; wiring the flags into an escalation trigger is Phase 3) |
| PRD-015 | No relevant guideline → explicit "no guideline found", no recommendation | `app/retrieval/confidence.py`, `app/agents/guideline_synthesis_agent.py` | — | not started — Phase 3 (needs the synthesis agent) |
| PRD-016 | Citations machine-verifiable against stored chunk text/offsets | `app/citations/model.py` (`verify_citation`, `build_citation`), `app/api/routes/corpus.py` (`GET /corpus/chunks/{chunk_id}`) | `tests/test_citation_model.py`, `tests/test_build_citation.py`, `tests/test_corpus_routes.py` | in progress (Phase 1 — verifier implemented; Phase 2 — builder implemented, DEVIATIONS #46; Phase 4 — chunk re-verification endpoint implemented) |

### 1.3 Multi-agent orchestration, memory & tools

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-020 | Multi-agent orchestration layer (LangGraph) with tool use | `app/agents/graph.py` (`build_graph`, real `StateGraph`), `app/agents/state.py`, `app/agents/*_agent.py` | `tests/test_agent_graph.py`, `tests/test_scope_boundary.py` | **done** (Phase 3 — real compiled graph, routing verified end-to-end offline via `MemorySaver`; real-Postgres checkpointer run verified too — DEVIATIONS #74, #82) |
| PRD-021 | Each agent bounded tool set + data scope; only patient-record agent has PHI access | `app/agents/registry.py`, `app/records/access.py` | `tests/test_agent_registry.py`, `tests/test_records_access.py` | **done** (Phase 3 — `get_patient_fields` never returns identifiers, audits every read; DB-backed per-role/purpose policy resolution stays Phase 4 — DEVIATIONS #70) |
| PRD-022 | Persistent memory: session conversation / per-patient context / reviewer history | `app/memory/conversation.py`, `app/memory/patient_context.py`, `app/db/models/memory.py` | `tests/test_memory_conversation.py`, `tests/test_memory_patient_context.py` | **done** (Phase 3 — verified against real Postgres: encrypted round-trip, accept/reject effects) |
| PRD-023 | Long agent runs checkpointed, resumable/inspectable | `app/memory/checkpointer.py` (`get_checkpointer`) | `tests/test_memory_checkpointer.py`, `tests/test_agent_graph.py` | **done** (Phase 3 — real `PostgresSaver`, DSN/privilege/schema fixes — DEVIATIONS #82; offline tests inject `MemorySaver`) |
| PRD-024 | Recommendation-shaped memory writes rejected; no cross-patient blending | `app/memory/patient_context.py` (`validate_patient_context_write`, `write_context`) | `tests/test_patient_context_rejects_recommendations.py`, `tests/test_memory_patient_context.py` | **done** (Phase 3 — persistence + accept/reject rollback; no cross-patient read API exists) |

### 1.4 Human-in-the-loop

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-030 | HITL escalation with defined triggers | `app/schemas/enums.py` (`EscalationTrigger`), `app/hitl/triggers.py`, `app/hitl/escalation.py`, `app/agents/escalation_agent.py` | `tests/test_hitl_escalation.py`, `tests/test_scope_boundary.py` | **done** (Phase 3) |
| PRD-031 | HITL rank mode (structured multi-domain rubric) | `app/schemas/rubric.py`, `app/rubric/domains.py`, `app/rubric/workflow.py`, `app/api/routes/rubric.py`, `frontend/src/components/RubricForm.tsx` | `tests/test_rubric.py`, `tests/test_rubric_workflow.py`, `tests/test_rubric_routes.py` | **done** (Phase 3 — capture, queue, real-Postgres verified through archival) |
| PRD-032 | HITL accept axis: full/partial/reject/out-of-scope with defined state effects | `app/hitl/decisions.py` (`apply_decision`, `apply_rating_accept_action`, `EFFECTS`), `app/schemas/hitl.py`, `app/schemas/rubric.py`, `frontend/src/components/AcceptAxisControls.tsx`, `frontend/src/acceptAxis.ts` | `tests/test_hitl_decisions.py`, `tests/test_hitl_routes.py`, `tests/test_rubric_workflow.py`, `tests/test_rubric_routes.py` | **done** (Phase 3 — verified against real Postgres, incl. reject rollback; `out_of_scope` added as a fourth action per operator direction, DEVIATIONS #84 — judges the request, not the answer. Phase 5 — a second entry point, `apply_rating_accept_action`, lets the accept axis be decided as part of a rank-mode rating submission, not only via escalation resolution — DEVIATIONS #99; that rank-mode path collects no reason code and never creates an escalation, unlike the escalation-resolution path — DEVIATIONS #100. `partial_accept` never requires an edited answer in either entry point — `accepted_context_ids` alone is a complete, valid `partial_accept` — DEVIATIONS #101) |
| PRD-033 | Every HITL action writes immutable audit + updates queue state | `app/hitl/decisions.py`, `app/hitl/escalation.py`, `app/audit/log.py` | `tests/test_hitl_decisions.py`, `tests/test_hitl_escalation.py` | **done** (Phase 3 — verified: audit chain intact after real HITL writes; rank-mode ratings themselves are not yet a distinct audit action — DEVIATIONS #80) |

### 1.5 Structured multi-rater evaluation

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-040 | 11-domain rubric, 5-pt Likert (incl. accuracy/safety/contextual/clarity) | `app/rubric/domains.py`, `app/schemas/rubric.py`, `app/db/models/eval.py` (`RubricDomain`) | `tests/test_rubric.py` | **done** (Phase 1 shape; Phase 3 — real DB seeding via `scripts/seed_db.py`, required by the FK from `rubric_rating.domain_code` — DEVIATIONS #81) |
| PRD-041 | Rubric scores stored as structured data (domain/score/rater/ts/result) | `app/db/models/eval.py` (`RubricRating`), `app/rubric/workflow.py` (`submit_rating`) | `tests/test_rubric_workflow.py`, `tests/test_rubric_routes.py` | **done** (Phase 3; Phase 5 — `submit_rating` now also requires and links the accept-axis decision for the same case in the same call, `RatingRound.accept_action_id`, per ARCH §13.2 "Both axes together" — DEVIATIONS #99. A ranker's task is exactly the rubric + the accept-axis pick — no reason code collected, no escalation ever created, and (if the pick is `partial_accept`) no edited-answer text required either — DEVIATIONS #100, #101) |
| PRD-042 | Workflow: rate → open queue → ≥3 distinct raters → IRR per domain → archive | `app/rubric/workflow.py`, `app/db/models/eval.py`, `app/rubric/tasks.py`, `app/api/routes/review_queue.py` | `tests/test_rubric_workflow.py`, `tests/test_review_queue_routes.py` | **done** (Phase 3 — verified end-to-end against real Postgres: 3 raters -> IRR -> archive) |
| PRD-043 | "Distinct clinician" enforced (no self / no duplicate-account double count) | `app/rubric/workflow.py` (`is_eligible_rater`), `app/db/models/eval.py` (`RatingRound` UNIQUE) | `tests/test_rubric.py`, `tests/test_rubric_workflow.py` | **done** (Phase 3 — application check + DB constraint; identity-fingerprint-based duplicate-*account* detection, distinct from duplicate-*rating* rejection, is Phase 4 (`iam.User.identity_fingerprint` field exists, unused)) |
| PRD-044 | IRR is a single named ordinal multi-rater metric (justified) | `app/rubric/irr.py` (`krippendorff_alpha_ordinal`, `per_domain_irr`) | `tests/test_rubric_irr.py` | **done** (Phase 3 — Krippendorff's alpha, ordinal; degenerate unanimous-rating case fixed after a real-Postgres run hit it — DEVIATIONS #81. Secondary stats (Gwet's AC2, ICC(2,k)) deferred, descriptive-only per ARCH — DEVIATIONS #77) |
| PRD-045 | Provenance tag `auto_generated`/`clinician_submitted`, visible throughout | `app/schemas/enums.py` (`Provenance`), `app/db/models/eval.py` (`eval_question.provenance`, `result.provenance`) | — | in progress (Phase 1 — enum + fields on models; `eval.result` row *creation* from a live answer/harness run is deferred — DEVIATIONS #79) |
| PRD-046 | Auto vs clinician results separately analysable, not pooled by default | `app/db/models/eval.py` (`IRRBatch.slice_definition`), `app/rubric/tasks.py` (`_run_compute_slice_irr`), `app/eval/harness.py` (`by_provenance`) | `tests/test_rubric_tasks.py`, `tests/test_eval_harness.py` | **done** (Phase 3 — slice filter never pools by default; harness report always breaks out `by_provenance`) |
| PRD-047 | Hard/adversarial cases included in the review queue | `app/rubric/workflow.py`, `app/api/routes/review_queue.py` | `tests/test_review_queue_routes.py` | **done** (Phase 3 — the queue has no expected-outcome filter, so hard cases are never excluded by construction) |
| PRD-048 | Purpose/limits statement: in-scope conformity evidence only | `app/rubric/__init__.py` (docstring), `app/rubric/irr.py` docstring, CDS-FUTURE.md | — | **done** (Phase 3 — stated in code docstrings; product-surface statement is Phase 5 frontend) |

### 1.6 Capability scope

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-050 | In scope: grounded guideline reporting/synthesis for hypotheticals | `app/agents/guideline_synthesis_agent.py`, `app/agents/prompts/guideline_synthesis.md`, `app/grounding/verifier.py` | `tests/test_guideline_synthesis_agent.py`, `tests/test_grounding_verifier.py` | **done** (Phase 3) |
| PRD-051 | In scope: patient stage-of-care classification (grounded, cited, non-directive) | `app/agents/stage_classifier_agent.py`, `app/records/criteria.py`, `app/agents/prompts/stage_classifier.md` | `tests/test_stage_classifier_agent.py`, `tests/test_records_criteria.py` | **done** (Phase 3 — criteria-field-to-record-path mapping is a curated synonym map, not a domain-matched ingest pipeline; stage label sourced from the criteria chunk's own heading — DEVIATIONS #71) |
| PRD-052 | In scope: missing-information identification (non-directive) | `app/agents/missing_info_agent.py`, `app/agents/prompts/missing_info.md` | `tests/test_missing_info_agent.py` | **done** (Phase 3 — released as reported content via `guideline_synthesis_agent`, not a HITL hold — DEVIATIONS #76) |
| PRD-053 | Out of scope: autonomous next-step recommendation (walled off, not implemented) | `app/agents/next_step_recommender.py` (interface stub, no logic; NOT in `app/agents/graph.py`'s `NODES`) | `tests/test_scope_boundary.py`, `tests/test_agent_graph.py` | **done** (Phase 3 — behavioural gate: 6 SCOPE-2.3/2.4 prompts through the real compiled graph, zero recommendation content) |
| PRD-054 | Out of scope: guideline adjustment for local constraints (walled off, not implemented) | `app/agents/local_adaptation_agent.py` (stub → `capability_not_enabled`) | `tests/test_scope_boundary.py` | **done** (Phase 3 — reachable only via the never-wired stub node; orchestrator routes `scope_2_excluded` straight to escalation, never to synthesis) |
| PRD-055 | Narrow exception: surface a documented alternative already in retrieved text | `app/scope/classifier.py`, `app/agents/guideline_synthesis_agent.py` (rule 6, `{{hospital_constraint}}`) | — | in progress (Phase 3 — prompt-level rule 6 + `hospital_constraint` passthrough exist; the `local_constraint_no_source_alt` escalation fallthrough when no documented alternative exists is not separately wired) |
| PRD-056 | Extension seam (named unimplemented agent / interface stub) | `app/agents/local_adaptation_agent.py`, `app/agents/next_step_recommender.py`, `app/agents/graph.py`, `app/config.py` (`local_adaptation_enabled`) | `tests/test_scope_boundary.py`, `tests/test_smoke.py` | **done** (Phase 1 seam; Phase 3 confirmed still inert and unreachable in the real compiled graph) |

### 1.7 Auto-generated hypothetical question set

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-060 | Auto-generated hypothetical question utility (record → narrative) | `app/eval/question_gen/generate.py`, `app/eval/question_gen/planner.py` | `tests/test_question_gen_generate.py` | in progress (Phase 2 — `generate_question` implements ARCH §15.1 steps 3-6 for an already-chosen source record: field extraction, LLM-generated narrative via `LLMGateway`, validation + retry, labelling. Source-record selection (step 2), diversity filter (step 7), gold re-check (step 8) deferred — DEVIATIONS #67) |
| PRD-061 | Narrative generation follows the no-fabrication discipline | `app/eval/question_gen/validate.py` | `tests/test_question_gen_validate.py` | in progress (Phase 2 — `validate_narrative` implemented: deterministic word-overlap against the record's own field values, with a rejected-and-corrected prompt design along the way — DEVIATIONS #66) |
| PRD-062 | Generated questions diverse across guideline topics/sections | `app/eval/question_gen/generate.py` (dedup), `app/eval/question_gen/planner.py` | — | not started |
| PRD-063 | Expected-outcome label (`well_supported`/`missing_info_expected`/`no_guideline_expected`) | `app/schemas/enums.py` (`ExpectedOutcome`), `app/db/models/eval.py` (`eval_question.expected_outcome`) | `tests/test_question_gen_composition.py` | in progress (Phase 1 — enum + field, separate from provenance) |
| PRD-064 | Deliberate hard cases: sparse records + corpus gaps | `scripts/generate_synthetic_records.py` (sparse fraction), `app/eval/question_gen/generate.py` | `tests/test_synthetic_generator.py` | in progress (Phase 1 — sparse-record generation; corpus-gap cases + record selection for `missing_info_expected`/`no_guideline_expected` are step 2, deferred — DEVIATIONS #67) |
| PRD-065 | 60/20/20 composition; hard cases ≤ 50% — documented decision | `app/eval/question_gen/planner.py` (`Composition`) | `tests/test_question_gen_composition.py` | in progress (Phase 1 — planner enforces split + cap) |
| PRD-066 | Auto Q/A used for fixed test set + queue seeding, kept separable | `app/db/models/eval.py` (`eval_question.in_fixed_testset`, provenance), `app/eval/tasks.py` (`_run_generate_questions`) | `tests/test_eval_tasks.py` | **done** (Phase 3 — `generate_questions` task now persists `eval_question` rows, closing the Phase-2-flagged "returns a dict; a caller writes it to the DB" gap — DEVIATIONS #67, #78; review-queue seeding from these is PRD-047/eval.result creation, still deferred per DEVIATIONS #79) |

### 1.8 Evaluation harness

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-070 | Eval harness: retrieval precision/recall + citation accuracy vs a fixed synthetic set | `app/eval/harness.py` (`run_harness`), `app/eval/metrics.py`, `app/eval/run.py` (CLI) | `tests/test_eval_harness.py`, `tests/test_eval_metrics.py`, `tests/test_eval_run_cli.py` | **done** (Phase 3 — runs the real compiled graph per fixed-testset question; metrics computed and gated) |
| PRD-071 | Harness scores pass/fail vs the expected-outcome label | `app/eval/metrics.py` (`expected_outcome_pass`) | `tests/test_eval_metrics.py` | **done** (Phase 3 — a recommendation-shaped answer is an automatic fail regardless of what was expected) |
| PRD-072 | Harness runs reproducible: pinned corpus snapshot + config | `app/db/models/eval.py` (`EvalRun.config_snapshot`) | `tests/test_eval_harness.py` | in progress (Phase 3 — `config_snapshot` pins model ids/thresholds on every run; `corpus_snapshot_id` field exists but nothing yet populates a `corpus.corpus_snapshot` row to reference — no corpus has been ingested end-to-end in this build) |
| PRD-073 | Harness reports by expected-outcome type and auto vs clinician subsets | `app/schemas/eval.py` (`EvalRunReport.by_provenance`, `.expected_outcome_pass`), `app/eval/harness.py` | `tests/test_eval_harness.py` | **done** (Phase 3) |

### 1.9 Security, privacy & safety

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-080 | All patient-record fields PHI by default, all environments | `app/schemas/record.py`, `app/db/models/records.py` (`patient.data_class`), `app/api/routes/records.py` | `tests/test_ingest_deidentified.py`, `tests/test_ingest_records_persistence.py`, `tests/test_records_routes.py` | in progress — **Checkpoint 1 (applied):** `data_class ∈ {synthetic, deidentified}` (DEVIATIONS #33, #37, #38). Phase 2: `payload_enc` envelope encryption + `mrn_hash` lookup-only dedup implemented and verified against a real Postgres (DEVIATIONS #57). Phase 4: `GET /records/{patient_id}/fields` and `GET /records/{patient_id}` implemented — `clinician`-only, RLS-scoped to the path `patient_id`, values endpoint gated by `record_field_policy` (DEVIATIONS #89). |
| PRD-081 | No real, non-de-identified PHI; synthetic OR attested de-identified | `app/ingestion/records.py` (`guard_batch`, `DatasetAttestation`), `scripts/ingest_deidentified_records.py`, `scripts/generate_synthetic_records.py` | `tests/test_ingest_deidentified.py`, `tests/test_synthetic_generator.py` | in progress — **applied at Checkpoint 1 (C1 confirmed):** `guard_batch` accepts `synthetic` (marker) or attested `deidentified` (complete `DATASET.md`), else hard-rejects. PRD.md constraint #1 preamble + PRD-081 + PRD-C1 + PRD-A3 amended; CLAUDE.md §3 rule 1 amended (DEVIATIONS #33, #38). |
| PRD-082 | Encryption in transit for all communication | `deploy/nginx/nginx.conf`, `docker-compose.yml` | — | not started |
| PRD-083 | Encryption at rest for PHI incl. backups + free-text fields | `app/crypto/provider.py`, `app/db/models/*` (`*_enc` columns) | — | not started |
| PRD-084 | Field-level access control at API + data layer | `app/auth/rbac.py` (`resolve_field_effects`), `app/db/models/records.py` (`RecordFieldPolicy` + unique constraint), `app/records/access.py` (`get_patient_fields`), `app/agents/patient_record_agent.py`, `app/agents/missing_info_agent.py`, `scripts/seed_db.py`, `alembic/versions/e6bd710e1911_*.py`, `app/api/routes/records.py` | `tests/test_rbac.py`, `tests/test_records_access.py`, `tests/test_patient_record_agent.py`, `tests/test_missing_info_agent.py` | in progress — data-layer gate implemented, wired into `get_patient_fields`, RLS-scoped per patient at the two call sites that read PHI, and seeded with real default policy rows, all verified against a real ephemeral Postgres (DEVIATIONS #87, #88); API-layer `GET /records/*` routes still 501 stubs |
| PRD-085 | Immutable audit logging (who/what/when/chunks/model/response) | `deploy/postgres/init/01_schemas_roles.sql`, `app/db/models/audit.py`, `app/audit/log.py`, `app/hitl/escalation.py`, `app/hitl/decisions.py`, `app/records/access.py`, `app/memory/patient_context.py` | `tests/test_audit_append_only.py`, `tests/test_hybrid_retrieve.py`, `tests/test_db_models_timezone_aware.py` | **done** (Phase 1 schema/grants; Phase 2 `retrieval` action, DEVIATIONS #50/#56; Phase 3 — `record_access` (field reads + patient_context writes) and `hitl_action` (escalation create + accept-axis decisions) actions now write real events too, verified end-to-end against real Postgres including the append-only trigger rejecting UPDATE even for the table owner. Rubric ratings not yet audited — DEVIATIONS #80; scheduled chain-verifier job stays Phase 4) |
| PRD-086 | RBAC: clinician, reviewer, admin (+ service) | `app/auth/provider.py`, `app/auth/devjwt.py`, `app/auth/repository.py`, `app/auth/rbac.py`, `app/api/deps.py`, `app/api/routes/auth.py`, `app/api/routes/admin.py`, `app/db/models/iam.py` | `tests/test_devjwt.py`, `tests/test_auth_repository.py`, `tests/test_auth_routes.py`, `tests/test_admin_routes.py` | in progress (Phase 4 — real dev-JWT issuance + verification, `current_principal` requires a valid token; per-role route guards via `require_role` in place across every route family; `resolve_field_effects` field-policy enforcement implemented, DEVIATIONS #87; `GET /admin/audit` implemented, DEVIATIONS #93) |
| PRD-087 | Disclaimer layer, non-removable; agents defer to the human clinician | `app/schemas/query.py` (`DISCLAIMER_TEXT`), `app/agents/orchestrator.py` (`_finalize`), `frontend/src/components/DisclaimerBanner.tsx`, `app/agents/prompts/*.md` | `tests/test_orchestrator.py`, `tests/test_query_route.py` | **done** (Phase 3 — every `POST /query` response carries the disclaimer via `QueryResponse`'s non-optional field, whether released or escalated) |
| PRD-088 | No independent diagnostic/treatment content; output filter | `app/grounding/wording.py`, `app/grounding/verifier.py`, `app/agents/orchestrator.py` (second wording pass on assembled framing text) | `tests/test_grounding_wording.py`, `tests/test_grounding_verifier.py`, `tests/test_orchestrator.py` | **done** (Phase 3 — directive-phrasing AND dosing-beyond-source checks; applied to every claim segment in the grounding gate, and again to assembled framing text at final assembly) |
| PRD-089 | No training on PHI; no PHI to external services; no PHI telemetry | `app/llm/gateway.py`, `app/logging.py` (redaction) | — | not started |
| PRD-090 | Ingested document text treated as untrusted (prompt-injection hardening) | `app/agents/prompts/*.md`, `app/agents/__init__.py` (rules) | — | not started |

### 1.10 Platform, config & deployment

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-100 | Backend in Python (FastAPI) | `app/main.py`, `app/api/**` | `tests/test_smoke.py` | in progress (Phase 1 — app factory + router + route stubs) |
| PRD-101 | LLM model id from env/config w/ placeholder; flag unverifiable names | `app/config.py` (`validate_model_config`), `app/llm/gateway.py` | `tests/test_config_model_verification.py` | in progress (Phase 1 — config + startup check + no-literal test; Phase 2 — `LLMGateway.chat()` HTTP call implemented, DEVIATIONS #54) |
| PRD-102 | Self-hosted LLM gateway with fallback routing | `app/llm/gateway.py` (`model_chain`), `app/llm/stub_server.py` | `tests/test_config_model_verification.py`, `tests/test_llm_gateway.py` | in progress (Phase 1 — chain + stub server; Phase 2 — real `POST /v1/chat/completions` call with per-model retry + fallback, tested offline via `httpx.MockTransport`, DEVIATIONS #54) |
| PRD-103 | Embedding + reranker model ids config-driven w/ placeholders | `app/config.py`, `app/ingestion/embed.py`, `app/retrieval/rerank.py` | — | in progress (Phase 1 — config surface + stub backends) |
| PRD-104 | One self-hosted vector store, justified | `app/retrieval/vectorstore.py` (Qdrant adapter), `docker-compose.yml` | — | in progress (Phase 1 — adapter interface + service) |
| PRD-105 | Redis + Celery for async ingestion + long agent tasks | `app/worker.py`, `app/ingestion/tasks.py`, `app/eval/tasks.py` (`generate_questions`, `run_harness_task`), `app/rubric/tasks.py` (`compute_result_irr_and_archive`, `compute_slice_irr`), `app/agents/tasks.py` (`run_query`), `app/agents/query_pipeline.py`, `app/agents/graph_runtime.py`, `app/api/routes/query.py` (`POST /query/async`, `GET /query/jobs/{job_id}`), `docker-compose.yml` | `tests/test_eval_tasks.py`, `tests/test_rubric_tasks.py`, `tests/test_agents_tasks.py`, `tests/test_query_route.py` | **done** — Phase 2 ingestion tasks; Phase 3 eval + rubric tasks; Phase 4 `run_query` (async long-running agent runs), additive to the unchanged synchronous `POST /query` (DEVIATIONS #94). Verified end-to-end against a real Redis broker + a real separate Celery worker process + real Postgres persistence. |
| PRD-106 | Docker/docker-compose; core flows work offline | `docker-compose.yml`, `Makefile`, `app/llm/stub*.py`, `.env.example`, `deploy/nginx/nginx.conf`, `app/main.py` (checkpointer startup warm-up) | — | **done** — Phase 1 compose stack + offline stubs; Phase 4: full `dev`-profile `docker compose up` end-to-end verified for real — proxy TLS + routing, migrate, seed, document ingestion through `worker`, `POST /query` (+ async), `GET /admin/audit`. Six real bugs found and fixed in the process (nginx prefix-stripping, a missing shared upload volume, a host/container UID permission mismatch, a checkpointer-setup self-deadlock, an audit hash-chain concurrency race, and a second deadlock from the first fix) — see DEVIATIONS #95 for the full account. |
| PRD-107 | React frontend: query UI + citation display + 3 HITL modes | `frontend/src/**` | — | **done** — Phase 1 UI shell; Phase 5: real auth (`POST /auth/dev-login`), wired query interface + citation display, rank mode (queue -> rubric + accept axis, submitted together in one action per case -> submit), plus a separate standalone accept-axis workflow (escalation discovery -> full_accept/partial_accept/reject/out_of_scope). Verified via real backend integration (login, query, rubric, full escalation lifecycle) through the Vite dev proxy — no browser-automation tool available this session for visual/interaction testing (DEVIATIONS #98, corrected by #99 for the combined rank+accept submission). |
| PRD-108 | Config via env/files; no hardcoded secrets; configurable secrets backend | `app/config.py`, `.env.example`, `app/crypto/provider.py` | — | in progress (Phase 1 — pydantic-settings + SECRETS_BACKEND; vault Phase 4) |

### 1.11 Non-functional requirements

| ID | Requirement (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| PRD-NFR-1 | Soft latency target (~15 s p50) documented, not enforced | ARCHITECTURE.md §NFR | — | deferred (documented target only) |
| PRD-NFR-2 | Safe degradation: never an ungrounded answer on component failure | `app/grounding/verifier.py`, `app/agents/orchestrator.py`, `app/api/routes/query.py` (pipeline-exception -> 502, never a partial answer), `frontend/src/components/AnswerView.tsx` | `tests/test_query_route.py`, `tests/test_orchestrator.py` | **done** (Phase 3 — an unhandled pipeline exception returns 502 with no answer body, never a partial/ungrounded one; grounding-gate escalation paths hold rather than release) |
| PRD-NFR-3 | Reproducibility: pinned deps + pinned eval config | `backend/pyproject.toml`, `backend/requirements-lock.txt`, `backend/.dockerignore`, `app/db/models/corpus.py` (`CorpusSnapshot`) | verified via a real `pip install -r requirements-lock.txt` + full local `pytest` run (73 passed) and a real `docker build` (exit 0, 6.52GB, 67 passed/2 skipped/0 errors inside the image) (DEVIATIONS.md #45/#45a) | in progress — dependency pinning done at Checkpoint 1 (ahead of the original Phase 2 plan, prompted by a real dependency-drift bug it fixed, plus a pip-26/opcode bug and a missing `.dockerignore` found along the way); eval-config pinning (`CorpusSnapshot`) remains Phase 2/3 |
| PRD-NFR-4 | Observability: structured logs, basic metrics, propagated trace IDs | `app/logging.py`, `app/api/middleware.py` | — | in progress (Phase 1 — logging + request-id middleware shell) |
| PRD-NFR-5 | Data minimisation: least-privilege fields; record vectors off by default | `app/config.py` (`patient_record_vectors_enabled`), `app/agents/registry.py` | `tests/test_agent_registry.py` | in progress (Phase 1 — flag + allow-lists) |
| PRD-NFR-6 | Portability: single-host docker-compose, no managed cloud for core | `docker-compose.yml` | — | in progress (Phase 1) |

### 1.12 Build constraints

| ID | Constraint (short) | Enforced by | Test(s) | Status |
|---|---|---|---|---|
| PRD-C1 | No real, non-de-identified PHI, ever — synthetic OR operator-attested de-identified | `scripts/generate_synthetic_records.py`, `scripts/ingest_deidentified_records.py`, `app/ingestion/records.py`, CLAUDE.md §3 | `tests/test_synthetic_generator.py`, `tests/test_ingest_deidentified.py` | in progress — **applied at Checkpoint 1 (C1 confirmed):** wording amended in PRD.md + CLAUDE.md; de-identified data admitted only with attestation and handled as PHI end to end (DEVIATIONS #33, #38) |
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
| ARCH-002 | Vector store: Qdrant (justified vs Chroma) | `app/retrieval/vectorstore.py`, `docker-compose.yml` | `tests/test_vectorstore.py` | in progress (Phase 2 — `QdrantVectorStore` implemented: `ensure_collection` with dense-dim assertion, `upsert_chunks`, server-side RRF `hybrid_search`, `get_by_ids`; verified against qdrant-client's embedded `:memory:` mode, DEVIATIONS #49) |
| ARCH-003 | Retrieval: dense + sparse BM25 + cross-encoder rerank, RRF fusion | `app/retrieval/hybrid.py`, `app/retrieval/rerank.py` | `tests/test_hybrid_retrieve.py` | in progress (Phase 2 — `retrieve()` implemented end to end; see PRD-010) |
| ARCH-004 | Embedding model config-driven (placeholder, flagged) | `app/config.py`, `app/ingestion/embed.py` | `tests/test_config_model_verification.py`, `tests/test_embed.py` | in progress — Checkpoint 1: `embedding_gateway_url`/`embedding_gateway_api_key` settings scaffolded (DEVIATIONS.md #42). Phase 2: `stub` and `local` (`sentence-transformers.SentenceTransformer`, query/doc prefixes, `lru_cache` singleton) backends implemented and unit-tested via dependency injection — not run against real model weights this session (DEVIATIONS #51). `gateway` branch remains `NotImplementedError` |
| ARCH-005 | `LLMGateway`: `MODEL_ID` + fallbacks from config; startup model-name verification | `app/config.py`, `app/llm/gateway.py` | `tests/test_config_model_verification.py`, `tests/test_llm_gateway.py` | in progress (Phase 2 — `chat()` implemented against an OpenAI-ish `/v1/chat/completions` contract matching `stub_server.py`; transport-security warning for plaintext external gateways, `validate_gateway_transport`, DEVIATIONS #54; `embed`/`rerank` on this class stay `NotImplementedError` — not the real dispatch points, see their own modules) |
| ARCH-006 | Orchestration: LangGraph | `app/agents/graph.py`, `app/agents/state.py` | `tests/test_smoke.py` | in progress (topology + state) |
| ARCH-007 | Async: Redis + Celery | `app/worker.py`, `app/agents/tasks.py`, `docker-compose.yml` | `tests/test_agents_tasks.py` | in progress — ingestion/eval/rubric/query all have real Celery task bodies now; `worker.py`'s `include` list covers all four task modules (DEVIATIONS #94) |
| ARCH-008 | PostgreSQL single system of record (7 schemas) | `app/db/models/**`, `app/db/session.py`, `deploy/postgres/init/01_schemas_roles.sql`, `backend/alembic/**` | `tests/test_audit_append_only.py`, `tests/test_initial_migration.py` | in progress (Phase 2 — the real initial migration (`alembic revision --autogenerate`) implemented, creating all 28 tables across 7 schemas; verified end-to-end against a real Postgres — upgrade, downgrade, re-upgrade. Required a new elevated `ALEMBIC_DATABASE_URL` since the app's runtime role has no CREATE privilege, DEVIATIONS #61) |
| ARCH-009 | Deploy: Docker + docker-compose, offline core flows | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | — | in progress |
| ARCH-010 | Frontend: React (Vite + TS), static | `frontend/**` | — | **done** — real `npm run build`/`npm run lint` clean, `frontend/Dockerfile` builds (nginx-served static SPA); `eslint.config.js` added (Phase 1 scaffold predated ESLint 9's flat-config requirement, `npm run lint` didn't actually run before, DEVIATIONS #98) |
| ARCH-011 | Auth: OIDC-ready `AuthProvider`, dev-JWT for MVP; roles | `app/auth/**`, `app/api/routes/auth.py`, `app/db/models/iam.py` | `tests/test_devjwt.py`, `tests/test_auth_repository.py`, `tests/test_auth_routes.py` | in progress (Phase 4 — `DevJwtProvider` HS256 mint/verify + `POST /auth/dev-login` implemented and tested; OIDC adapter still a stub, DEVIATIONS #86) |
| ARCH-012 | Reranker: config-driven cross-encoder, **decided to run locally** (placeholder model id, flagged) | `app/config.py`, `app/retrieval/rerank.py` | `tests/test_rerank.py` | in progress — Checkpoint 1: **`RERANKER_BACKEND=local` decided** (DEVIATIONS.md #44). Phase 2: `stub` and `local` (`sentence-transformers.CrossEncoder`, device resolution, `lru_cache` singleton) implemented and unit-tested via dependency injection — not run against real model weights this session (DEVIATIONS #51); the `asyncio.to_thread` offload + startup warm-load are `app.retrieval.hybrid` / `app.main`'s job (Phase 2/4). `gateway` is not a supported path for this requirement |
| ARCH-013 | Chunking: profile-aware, atomic on the citable unit | `app/ingestion/chunking.py`, `app/db/models/corpus.py` | `tests/test_chunking.py` | in progress (Phase 2 — `chunk_document` implements rules 0/1/1b/2/3/3b/4/5/6: GRADE-marker recommendation + protocol-step atomicity with oversized-recommendation sentence-splitting (`split_group_id`), 350–600-token prose windowing with ~15% overlap, table/criteria/figure chunk types, embedding-text breadcrumb prefix, parent linkage; known heuristic limits logged (DEVIATIONS #47)) |
| ARCH-038 | *(NEW — defined at Checkpoint 1)* Document ingest metadata is operator-supplied via a per-file manifest, never inferred from PDF metadata; adds `document.licence`, `document_version.format_profile`/`parse_quality`, `chunk.figure_ref` | `app/db/models/corpus.py`, `app/ingestion/documents.py`, `data/sample_guidelines/manifest.example.json`, `scripts/prepare_sample_guidelines.py`, `app/api/routes/ingest.py`, `app/schemas/ingest.py` | `tests/test_prepare_guidelines.py`, `tests/test_document_persistence.py`, `tests/test_ingest_routes.py` | in progress — ARCH §3/§4.1/§5.1 define it; models + manifest + validator in place (DEVIATIONS #29, #31). Phase 2: `create_or_supersede_document_version` implements manifest-driven `document`/`document_version` creation + idempotency-on-`content_sha256` + supersession (DEVIATIONS #59); `POST /ingest/documents` is the HTTP path to it (multipart form carries the per-file manifest fields directly, ARCH-038's own convention — no separate manifest-file upload) — DEVIATIONS #65 |
| ARCH-039 | *(NEW — defined at Checkpoint 1)* Patient-data classes (`synthetic` \| attested `deidentified`), EAV/long ingestion via a reusable pivot + declarative `field_mapping.yaml`, a `PatientDataSource` seam (`FileEavSource` now, `RestApiPullSource` stub), and **`record.py` design principles** (flat, source-agnostic, temporal `started_at`/`stopped_at` pair, additive-only, `schema_version`-gated) | `app/ingestion/eav.py`, `app/ingestion/sources/`, `app/ingestion/records.py`, `app/schemas/enums.py` (`DataClass`), `app/schemas/record.py` (v1.3.0 + design notes), `app/db/models/records.py` (`patient.data_class`, `patient.mrn_hash`, `patient_record.dataset_id`), `scripts/ingest_deidentified_records.py`, `app/api/routes/ingest.py`, `data/patient_records/deidentified/newborn_nbu_2021/{field_mapping.yaml,DATASET.md}` | `tests/test_eav_mapping.py`, `tests/test_ingest_deidentified.py`, `tests/test_ingest_records_persistence.py`, `tests/test_ingest_routes.py` | in progress — ARCH §3/§4.2/§5.2/§17.1/§20 + ESSENTIALS §1a define it; pivot + mapping + sources + guard + models + scripts + tests in place (DEVIATIONS #33–#35, #38, #39). Phase 2: DB persistence implemented + verified against a real Postgres (DEVIATIONS #57); `POST /ingest/records/eav` is the HTTP path to the same `FileEavSource` pipeline (`mapping_ref` resolution, DEVIATIONS #65). `RestApiPullSource` (a future pull-API, not this HTTP push path) remains a stub. |
| ARCH-014 | Citation object schema (min: doc id + version + section/page + chunk offset + quote) | `app/schemas/citation.py`, `app/citations/model.py` | `tests/test_citation_model.py` | in progress |
| ARCH-015 | Grounding gate: citation-resolves / quote-integrity / entailment / scope-wording | `app/grounding/verifier.py`, `app/grounding/wording.py`, `app/citations/model.py` | `tests/test_grounding_wording.py`, `tests/test_citation_model.py` | in progress (deterministic parts scaffolded; entailment + verdict Phase 3) |
| ARCH-016 | Multi-agent topology (9 roles, LangGraph, per-node checkpoint, tool allow-lists) | `app/agents/graph.py`, `app/agents/registry.py`, `app/agents/*_agent.py` | `tests/test_agent_registry.py`, `tests/test_smoke.py` | in progress |
| ARCH-017 | Persistent memory stores (session conv / patient_context / rating history / checkpoints / hot state) | `app/memory/**`, `app/db/models/memory.py`, `app/db/models/eval.py` | — | in progress (models + validator) |
| ARCH-018 | HITL escalation trigger codes + lifecycle | `app/schemas/enums.py`, `app/hitl/triggers.py`, `app/hitl/escalation.py`, `app/api/routes/hitl.py` | `tests/test_scope_boundary.py`, `tests/test_hitl_escalation.py`, `tests/test_hitl_routes.py` | **done** — codes + release policy (Phase 3); full lifecycle now reachable via the API: `GET /hitl/escalations` (list, new) + `GET /hitl/escalations/{id}` (now wires the `open -> in_review` "reviewer pulls" transition) + `POST .../decision` (`resolved`) (Phase 5, DEVIATIONS #97) |
| ARCH-019 | HITL interaction modes (rank axis + accept axis) and their effect on state | `app/hitl/decisions.py` (`EFFECTS`, `apply_decision`, `apply_rating_accept_action`), `app/schemas/hitl.py`, `app/schemas/rubric.py`, `app/rubric/workflow.py`, `frontend/src/pages/ReviewPage.tsx`, `frontend/src/components/RubricForm.tsx`, `frontend/src/components/AcceptAxisControls.tsx`, `frontend/src/acceptAxis.ts` | `tests/test_hitl_decisions.py`, `tests/test_rubric_workflow.py`, `tests/test_rubric_routes.py` | **done** — backend Phase 3 (accept axis now 4 actions: full_accept/partial_accept/reject/out_of_scope, DEVIATIONS #84); Phase 5 frontend wires both per ARCH §13.2 "Both axes together" — for rank mode, one submission per case does the 11-domain rubric AND the accept-axis decision together (`RatingRound.accept_action_id -> HitlDecision`), while a standalone escalation-resolution workflow remains a separate, valid entry point for the escalation-held-answer case. Corrects #98's earlier "two independent workflows" framing — DEVIATIONS #99. A ranker's task is exactly those two things and nothing else: no reason/justification text collected in rank mode (the escalation-resolution path still requires one), and rank mode never creates an escalation (verified: `apply_rating_accept_action` always sets `escalation_id=None` and is never on any path that calls `create_escalation`) — DEVIATIONS #100. `partial_accept` never requires written text in either workflow — the accepted-context split alone is a complete, valid `partial_accept`, verified against real Postgres to still correctly drive the patient_context effect with no edited answer given — DEVIATIONS #101 |
| ARCH-020 | Multi-rater rubric workflow state machine + open queue + min-rater enforcement | `app/rubric/workflow.py`, `app/db/models/eval.py` | `tests/test_rubric.py` | in progress |
| ARCH-021 | IRR metric: Krippendorff's alpha (ordinal) per domain; secondary AC2/ICC | `app/rubric/irr.py` | — | not started (Phase 3) |
| ARCH-022 | Auto-generated hypothetical question set pipeline (60/20/20, validator, gold re-check) | `app/eval/question_gen/**` | `tests/test_question_gen_composition.py`, `tests/test_question_gen_generate.py`, `tests/test_question_gen_validate.py` | in progress (Phase 1 — planner + composition guard. Phase 2 — narrative generation + validation (steps 3-6) implemented; record selection, diversity filter, gold re-check (steps 2/7/8) remain — DEVIATIONS #67) |
| ARCH-023 | Patient-record vectorization OFF by default; separate collection if enabled | `app/config.py` (`patient_record_vectors_enabled`), `app/retrieval/vectorstore.py` | — | in progress (flag) |
| ARCH-024 | `patient_context` repo rejects recommendation-shaped writes; no cross-patient reads | `app/memory/patient_context.py` | `tests/test_patient_context_rejects_recommendations.py` | in progress |
| ARCH-025 | Scope enforcement: scope-classifier routes SCOPE-2.3/2.4 to escalation; no composing tool | `app/scope/classifier.py`, `app/hitl/triggers.py` (`NEVER_ANSWERED`), `app/agents/registry.py` | `tests/test_scope_boundary.py` | in progress (marker lists + never-answered set; classifier Phase 3) |
| ARCH-026 | Extension seam: `local-adaptation` agent stub + reserved `next-step-recommender` + inert flag | `app/agents/local_adaptation_agent.py`, `app/agents/next_step_recommender.py`, `app/agents/graph.py`, `app/config.py` | `tests/test_scope_boundary.py`, `tests/test_smoke.py` | in progress |
| ARCH-030 | Evaluation harness design (retrieval P/R, citation accuracy, expected-outcome pass/fail, subset reporting) | `app/eval/harness.py`, `app/eval/metrics.py`, `app/schemas/eval.py` | — | not started |
| ARCH-031 | Encryption in transit (TLS at proxy, private net, authenticated services) | `deploy/nginx/nginx.conf`, `docker-compose.yml` | — | in progress (proxy + private net; TLS certs Phase 4) |
| ARCH-032 | Encryption at rest (host volume + app envelope encryption for enumerated PHI fields) | `app/crypto/provider.py`, `app/db/models/*` (`*_enc`) | `tests/test_crypto_provider.py`, `tests/test_ingest_records_persistence.py` | in progress (Phase 2 — `FileKEKProvider` implements AES-256-GCM envelope encryption with AAD binding, DEVIATIONS #52; wired into `patient_record.payload_enc` and `patient.mrn_enc`, verified against a real Postgres (encrypt/decrypt round-trip, DEVIATIONS #57); audit `*_text_enc` columns remain unwired) |
| ARCH-033 | Key management (`SECRETS_BACKEND`, `CryptoProvider`, dev-key warning) | `app/crypto/provider.py`, `app/config.py` | `tests/test_crypto_provider.py` | in progress (Phase 2 — `file` backend generates + persists a 0600 dev KEK on first use, DEVIATIONS #52; `env`/`vault` backends remain Phase 4) |
| ARCH-034 | Access control (`AuthProvider`, RBAC + RLS + `record_field_policy` + per-agent tool allow-list + purpose-of-use) | `app/auth/**`, `app/api/deps.py`, `app/api/routes/auth.py`, `app/api/routes/records.py`, `app/agents/registry.py`, `app/agents/patient_record_agent.py`, `app/agents/missing_info_agent.py`, `app/records/access.py`, `app/db/session.py` (RLS GUC), `app/db/models/records.py`, `scripts/seed_db.py`, `backend/alembic/versions/ba3c23a19ce9_initial_schema.py`, `backend/alembic/versions/e6bd710e1911_*.py` | `tests/test_agent_registry.py`, `tests/test_initial_migration.py`, `tests/test_devjwt.py`, `tests/test_auth_routes.py`, `tests/test_rbac.py`, `tests/test_records_access.py`, `tests/test_patient_record_agent.py`, `tests/test_missing_info_agent.py`, `tests/test_records_routes.py` | in progress — tool allow-list enforced; Phase 2 RLS on `records.patient`/`records.patient_record`/`memory.patient_context` (DEVIATIONS #63); Phase 4: `current_principal` requires and verifies a real Bearer token (DEVIATIONS #86); `resolve_field_effects`/`record_field_policy` field-level gate implemented and wired into `get_patient_fields`; `session_scope(patient_scope=...)` set at the two agent call sites reading PHI and (via the new `get_patient_scoped_db` dependency) at `GET /records/*`, both routes now implemented (`clinician`-only + field-policy-gated, DEVIATIONS #89); `record_field_policy` has a real unique constraint and default seed rows — all verified together against a real ephemeral Postgres (DEVIATIONS #87, #88). Still outstanding: `memory.patient_context` writes are implemented (`write_context`) but not yet called from any live agent node — RLS on that table is untested by a real request; `GET /corpus/*` and `GET /admin/audit` route stubs. |
| ARCH-035 | Audit logging (append-only grants, hash chain, encrypted text + hashes, one event per action) | `deploy/postgres/init/01_schemas_roles.sql`, `app/db/models/audit.py`, `app/audit/log.py`, `app/api/routes/query.py`, `app/ingestion/corpus_access.py`, `backend/alembic/versions/ba3c23a19ce9_initial_schema.py` | `tests/test_audit_append_only.py`, `tests/test_initial_migration.py`, `tests/test_query_route.py`, `tests/test_corpus_access.py` | in progress — writers now real for `retrieval` (DEVIATIONS #50), `record_access` (`app.records.access`, `app.memory.patient_context`), `hitl_action` (`app.hitl.decisions`/`escalation`), `login` (`app.api.routes.auth`), `config_change` (`app.ingestion.corpus_access.withdraw_version`, DEVIATIONS #90), and now `query`/`answer` (`POST /query`, DEVIATIONS #91) — append-only enforced by a DB trigger, defense in depth beyond the role GRANTs (DEVIATIONS #63). `ingestion` (`app/api/routes/ingest.py`, all four routes, DEVIATIONS #92) closes the last of ARCH §18's action categories — every one now has a real writer. `query_text_enc`/`response_text_enc` are deliberately left unpopulated everywhere (hash-only, matching the existing `retrieval` precedent of never storing query text, even encrypted). **Concurrency:** a real chain-breaking race between two sessions writing audit rows for the same logical request was found and fixed via a `pg_advisory_xact_lock` in `_fetch_last_row_hash` (a first attempt, `SELECT ... FOR UPDATE`, was tried and confirmed not to work) — verified with real concurrent writers against a real Postgres, both directly and through a live `docker compose up` stack (DEVIATIONS #95). |
| ARCH-036 | Deployment architecture (compose services + profiles + non-root + healthchecks) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `deploy/**`, `app/main.py` | — | **done** — full `dev`-profile stack verified end-to-end against real requests (not just config inspection), six real bugs found and fixed (DEVIATIONS #95). Still outstanding: a durable fix for the host/container UID mismatch on the `data/` bind mounts (currently a manual `chmod`, not automated or documented as a setup step); `full` profile (keycloak, review-webhook) not separately verified. |
| ARCH-037 | Safety/disclaimer layer (non-removable disclaimer field, prompt framing, output filter) | `app/schemas/query.py`, `app/grounding/wording.py`, `app/agents/prompts/**`, `frontend/src/components/DisclaimerBanner.tsx` | `tests/test_grounding_wording.py` | in progress |

*(ARCH-027, ARCH-028, ARCH-029 intentionally unused — IDs are permanent and need not be contiguous.)*

---

## 3. Capability-scoping items (ARCHITECTURE.md §9)

| ID | Item (short) | Implementing file(s) | Test(s) | Status |
|---|---|---|---|---|
| SCOPE-1.1 | Hypothetical guideline-lookup → synthesized cited answer | `app/agents/guideline_synthesis_agent.py` | — | not started |
| SCOPE-1.2 | Reported-content framing enforced in every guideline-touching agent's prompt template + filter | `app/agents/prompts/*.md`, `app/grounding/wording.py` | `tests/test_grounding_wording.py` | in progress (prompt rules + directive filter) |
| SCOPE-1.3 | Explicit "no guideline found"; no general-knowledge fallback (incl. hypotheticals) | `app/retrieval/confidence.py`, `app/agents/guideline_synthesis_agent.py` | — | not started |
| SCOPE-1.4 | Auto-generated hypothetical question set is scope-1-framed | `app/eval/question_gen/generate.py`, `app/agents/prompts/orchestrator_scope.md` | `tests/test_question_gen_generate.py` | in progress (Phase 2 — `_is_scope1_framed` enforces the mandated "what does the guideline recommend..." shape and rejects directive/management-question phrasing after generation, independent of the prompt template itself; an operator-supplied draft prompt that asked for patient-specific management questions was flagged and corrected rather than adopted — DEVIATIONS #66) |
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
| PRD-A2 | Sample public guideline PDFs obtainable for dev; licences permit local use | deferred (assumption — **satisfied at Checkpoint 1** by 3 operator-provided PDFs: WHO ×2, Kenya MOH ×1; per-document **licence pending confirmation in `data/sample_guidelines/manifest.json`**, DEVIATIONS #29) |
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

## Summary counts (2026-08-27 end of Phase 1; updated 2026-09-01 at Checkpoint 1)

- Implementation requirements tracked: **PRD 0xx–1xx (66)** + **PRD-NFR (6)** +
  **PRD-C (8)** + **PRD-G (7)** + **ARCH (36, incl. ARCH-038 & ARCH-039 defined)** +
  **SCOPE (9)** = **132**
- Status: `in progress` ~70 (scaffolded contract + test) · `not started` ~60 ·
  `deferred` 1 (PRD-NFR-1) · `done` 0
- Tracked decisions (non-goals / assumptions / open questions): **23**, all `deferred`
- Backend test suite: **73 passing** at Phase 1 close, **233 passing** as of the
  2026-09-14 Phase 2 update below — offline (no DB / network / real models)
- **2026-09-01 Checkpoint 1 corrections** from operator-supplied guideline PDFs
  (**Approach A confirmed; applied**): rows PRD-001, PRD-002, PRD-003, PRD-004,
  PRD-006, PRD-051, PRD-052, ARCH-013, PRD-A2 updated; ARCH-038 added and
  defined. ARCHITECTURE.md §3/§4.1/§5.1/§5.2/§6/§8.3/§9.1/§15/§20/§21a and
  ARCHITECTURE-ESSENTIALS.md §2/§12 updated; `corpus` models,
  `prepare_sample_guidelines.py` + `manifest.example.json`, `generate_synthetic_records.py`
  (`--domain`, neonatal default), record schema v1.1.0, config/env/Makefile/README
  all applied. See DEVIATIONS #26–#32.
- **2026-09-01 Checkpoint 1 — operator-supplied de-identified newborn dataset**
  (EAV, ~40,871 patients): **C1/C2/C3 confirmed; applied** (DEVIATIONS #33–#38).
  Rows PRD-002, PRD-003, PRD-006, PRD-080, PRD-081, PRD-C1 updated; **ARCH-039**
  defined (ARCH §3/§4.2/§5.2/§17.1/§20). Applied: schema **v1.2.0**
  (`examination_findings[]`, `interventions[]`, `capillary_refill_seconds`;
  `given_name`/`family_name` optional — C2), `app/schemas/enums.DataClass`,
  `app/ingestion/eav.py` (pivot + `MappingSpec` + transforms), `app/ingestion/sources/`
  (`FileEavSource` + `RestApiPullSource` stub), `guard_batch` + `DatasetAttestation`,
  `records` models (`data_class`, `dataset_id`), `scripts/ingest_deidentified_records.py`,
  `/ingest/records/eav` stub, folder reorg to `data/patient_records/{synthetic,deidentified/<ds>}/`,
  `field_mapping.yaml` + `DATASET.md` for `newborn_nbu_2021`, `.gitignore` (no
  dataset file committable), config/env/Makefile/pyproject/README, PRD.md
  constraint #1 + PRD-081/C1/A3, CLAUDE.md §3 rule 1, ESSENTIALS §0/§11/§12.
  DB persistence, `/ingest/records/eav` body, and `RestApiPullSource` are Phase 2.
- **2026-09-02 Checkpoint 1 — record-schema temporal fields + design principles**
  (DEVIATIONS #39; still Checkpoint 1, applied): schema **→ v1.3.0**
  (`Medication.stopped_at`, `Intervention.stopped_at`); ARCHITECTURE.md §4.2
  gains "Record schema — design notes" (flat, source-agnostic, `started_at`/
  `stopped_at` for interval entities, additive-only, `schema_version`-gated) +
  ESSENTIALS §1a; `field_mapping.yaml` bumped, de-id meds/interventions
  `started_at` == `encounter.admitted_at` asserted; `record_schema.json`,
  `test_eav_mapping.py`, `test_ingest_deidentified.py` updated. **73 passing.**
- **2026-09-14 Phase 2 (in progress, user-approved start):** guideline parsing
  (`.pdf` via pypdf + `.md`/`.txt`) and format-profile-aware chunking (ARCH §6
  rules 0/1/1b/2/3/3b/4/5/6) implemented and tested; BM25-style sparse vectors
  (stable-hash indices + Qdrant server-side IDF, DEVIATIONS #48, superseding a
  first design with a real multi-batch correctness bug caught before anything
  was built on it) and the `QdrantVectorStore` adapter (verified against
  qdrant-client's embedded `:memory:` mode) implemented and tested; embedding
  (`local`) and reranker (`local`) backends implemented against the documented
  `sentence-transformers` API and unit-tested via dependency injection — not
  run against real model weights this session (DEVIATIONS #51); conflict
  detection (`app/retrieval/conflict.py`) implemented and tested; `build_citation`
  pulled into Phase 2 ahead of its original Phase 3 placeholder (DEVIATIONS
  #46); `FileKEKProvider` AES-256-GCM envelope encryption implemented and
  tested (DEVIATIONS #52). Rows updated: PRD-001, PRD-004, PRD-011, PRD-013,
  PRD-014, PRD-016, ARCH-002, ARCH-004, ARCH-012, ARCH-013, ARCH-032, ARCH-033.
  Audit-writer scope conflict (prompt.txt Phase 2 wants "basic audit logging on
  every retrieval"; the Phase-1 scaffold had deferred the writer to Phase 4)
  flagged to and resolved by the operator: a minimal `retrieval`-event writer
  implemented (DEVIATIONS #50) and wired into the retrieval pipeline.
  `LLMGateway.chat()` implemented against an OpenAI-ish `/v1/chat/completions`
  contract with per-model retry/fallback and a transport-security warning for
  plaintext non-local gateways (DEVIATIONS #54). `app.retrieval.hybrid.retrieve`
  implemented end to end (query construction with a curated abbreviation map,
  DEVIATIONS #55; Qdrant dense+sparse search; server-side RRF; rerank;
  confidence; conflict detection; retrieval snapshot; optional audit write),
  verified against qdrant-client's embedded `:memory:` mode. Verifying the
  audit writer against a **real** (ephemeral Docker) Postgres surfaced and fixed
  a genuine bug: 13 `datetime` columns across `audit`/`hitl`/`eval`/`memory`/
  `records`/`corpus`/`iam` were timezone-naive (`DateTime()` without
  `timezone=True`), silently dropping tzinfo on every round-trip and breaking
  the audit hash chain's own verification — fixed, and guarded going forward
  by an offline structural test, `tests/test_db_models_timezone_aware.py`
  (DEVIATIONS #56). Rows updated (this entry, beyond the ones listed above):
  PRD-010, PRD-085, PRD-101, PRD-102, ARCH-003, ARCH-005, ARCH-035.
  Remaining Phase 2 work: DB persistence for ingested documents/chunks/records,
  the real Alembic migration (autogenerate + RLS + audit trigger), and the
  auto-generated hypothetical question utility (`question_gen/generate.py` +
  `validate.py`). **144 passing** (was 73 at Phase 1 close).
- **2026-09-14 Phase 2 continued — DB persistence for ingested documents/chunks/records:**
  `app.ingestion.records.ingest_records` persists `patient`/`patient_record`
  rows (dedupe on MRN via a new `patient.mrn_hash` lookup column +
  `CryptoProvider.deterministic_hash`, since `mrn_enc` alone — randomly-nonced
  AEAD — can't support a dedupe lookup, DEVIATIONS #57); wired into
  `scripts/ingest_deidentified_records.py --persist`. `app.ingestion.documents.
  create_or_supersede_document_version` implements manifest-driven `document`/
  `document_version` creation, idempotency on `content_sha256`, and
  supersession (DEVIATIONS #59 — the "newer" heuristic; PRD-Q1 remains open for
  the harder cases). `app.ingestion.chunk_persistence.persist_chunks` +
  `app.ingestion.tasks._run_process_document` implement the real parse -> chunk
  -> embed -> persist `corpus.chunk` rows (resolving `parent_ordinal` -> real
  `parent_chunk_id`) -> upsert Qdrant pipeline, with chunk-level topic tagging
  reusing each document's own manifest `topic_tags` as the keyword map
  (DEVIATIONS #58). `app.api.deps.get_db` wired to a real session
  (`app.db.session.session_scope`). All of the above verified end-to-end
  against a real (ephemeral, Dockerized) Postgres + a real Qdrant
  (`:memory:` mode) — not just offline mocks. `process_record_batch` and
  `reembed_corpus` remain unimplemented (DEVIATIONS #60: both need
  infrastructure ARCH doesn't yet specify). Rows updated: PRD-001, PRD-002,
  PRD-004, PRD-080, ARCH-032, ARCH-038, ARCH-039. **172 passing** (was 144).
- **2026-09-14 Phase 2 continued — the real initial Alembic migration:**
  `alembic revision --autogenerate` run against every model in
  `app/db/models/` (0001's own docstring instruction), chained after the
  Phase-1 placeholder, creating all 28 tables across the 7 managed schemas.
  Hand-extended with what autogenerate cannot produce: row-level security on
  `records.patient`/`records.patient_record`/`memory.patient_context`, keyed
  on `app.current_patient_scope`, fail-open when unset so every
  already-verified ingestion/persistence path (none of which set that GUC)
  keeps working (DEVIATIONS #63); and a `BEFORE UPDATE OR DELETE` trigger on
  `audit.audit_event` that rejects both even for the table-owning role —
  defense in depth beyond the existing REVOKE. Surfaced and fixed a real
  latent gap along the way: the app's runtime `DATABASE_URL` role (`hrag_app`)
  has no `CREATE` privilege, so Alembic needed its own elevated
  `ALEMBIC_DATABASE_URL` (defaults to the already-provisioned `hrag_admin`
  superuser) — never used by the running app (DEVIATIONS #61). The
  `memory.langgraph_checkpoint` placeholder table is explicitly excluded from
  Alembic's management — `langgraph-checkpoint-postgres` owns that table's
  lifecycle via its own `PostgresSaver.setup()` (DEVIATIONS #62). Verified
  end-to-end against a real (ephemeral, Dockerized) Postgres: upgrade,
  RLS-enforced-for-hrag_app-but-not-for-the-owner, trigger-blocks-owner-too,
  downgrade, re-upgrade, and `ingest_records` re-run successfully as `hrag_app`
  against the fully-migrated schema. Rows updated: ARCH-008, ARCH-034,
  ARCH-035. **181 passing** (was 172).
- **2026-09-14 Phase 2 continued — the `/ingest/*` HTTP routes:** all four
  endpoints wired to real persistence for the first time (previously 501
  stubs): `POST /ingest/documents` (multipart upload + manifest-shaped form
  fields -> `create_or_supersede_document_version` -> enqueues
  `process_document`; `409` on a same-name/different-content file conflict,
  DEVIATIONS #65), `POST /ingest/records/file` (JSON full-fidelity / CSV
  scalar-only via `parse_wide_upload`, DEVIATIONS #64), `POST /ingest/records/eav`
  (reuses `FileEavSource`, `mapping_ref` resolved against the same
  `PATIENT_RECORDS_DIR/deidentified/<name>/field_mapping.yaml` convention the
  CLI script and the bundled dataset already use, DEVIATIONS #65), and
  `POST /ingest/records` (JSON body, `RecordIngestBatch`, 500-record bound per
  call). New `app/schemas/ingest.py` (`DocumentIngestResponse`,
  `RecordIngestResponse`). `app.api.deps.get_db` (already wired) used as the
  real DB dependency; all four routes tested via FastAPI's `TestClient` with
  `get_db`/`current_principal` dependency-overridden (the dev auth fallback
  only ever grants `"clinician"`, and real RBAC is Phase 4 — this is the
  standard way to test a role-gated route before real auth exists, not a
  workaround) and `process_document.delay` monkeypatched (no real Celery
  broker needed). Rows updated: PRD-001, PRD-002, PRD-003, ARCH-038, ARCH-039.
  **208 passing** (was 181).
- **2026-09-14 Phase 2 continued — the auto-generated hypothetical question
  utility (ARCH §15.1 steps 3-6):** the operator supplied a draft
  question-generation prompt for review before implementation; it was found
  to ask for patient-specific SBI *management* questions ("management of
  suspected or confirmed SBI" for "this patient"), which risks generating
  SCOPE-2.3-adjacent next-step-recommendation questions rather than ARCH
  §15.1 step 4's mandated scope-1 guideline-lookup shape — flagged per
  CLAUDE.md §3 rule 4 before writing any code, corrected, then implemented
  (DEVIATIONS #66). `app.eval.question_gen.validate.validate_narrative`
  implemented (deterministic word-overlap against the record's own field
  values, not a medical NER model — a documented approximation).
  `app.eval.question_gen.generate.generate_question` implemented (structured
  field extraction, `LLMGateway`-driven narrative generation with a
  scope-1-only template, double-enforced scope framing via
  `_is_scope1_framed`, validation + reject-and-retry up to
  `QGEN_MAX_RETRIES`). Tested offline via a dedicated fake chat gateway,
  distinct from the production `stub_chat` (which deliberately never
  generates real content). Source-record selection (step 2), the diversity
  filter (step 7), and the gold re-check (step 8) are **not** implemented —
  all three need a populated, ingested corpus this build hasn't run
  end-to-end yet (DEVIATIONS #67). Rows updated: PRD-060, PRD-061, PRD-064,
  ARCH-022, SCOPE-1.4. **233 passing** (was 208).

  **This closes out the Phase 2 checklist** (`prompt.txt`): document/record
  ingestion + chunking, hybrid retrieval, citation generation, basic audit
  logging on retrieval, the real Alembic migration, the `/ingest/*` HTTP
  routes, and the auto-generated question utility are all implemented and
  tested. Ready for Checkpoint 2 review.

- **2026-09-14 Checkpoint 2 approved.** Phase 3 (Multi-Agent Orchestration &
  HITL) begun.

- **2026-09-14 Phase 3 — Multi-Agent Orchestration & HITL:** implemented,
  with tests, the full `prompt.txt` Phase 3 checklist.
  - **Agent topology (LangGraph, real `StateGraph`):** all 7 active agents
    (orchestrator, retrieval, patient_record, stage_classifier,
    missing_info, guideline_synthesis, citation_verifier) plus escalation
    implemented; `app.agents.graph.build_graph()` assembles and compiles the
    real graph with deterministic conditional routing (never a model call
    for routing decisions). `local_adaptation`/`next_step_recommender` stubs
    confirmed still inert and unreachable. Scope classification
    (`app.scope.classifier`) is a deterministic lexical backstop only — no
    model call for the highest-stakes decision in the system (DEVIATIONS
    #68). New build-gating test `test_scope_boundary.py` runs 6
    SCOPE-2.3/2.4-style prompts through the real compiled graph end-to-end
    and asserts `trigger_code=scope_boundary` + zero recommendation content.
  - **Grounding gate:** `app.grounding.verifier.verify` implements the full
    ARCH §8.3 verdict policy (release / release_marked / partial_strip /
    escalate); citation resolution is positional (`c1..cN` labels, not
    requiring the model to reproduce chunk UUIDs verbatim — DEVIATIONS #69);
    entailment is hybrid lexical+model, calling the model only on ambiguous
    overlap. `app.grounding.wording` extended with a dosing-beyond-source
    check.
  - **SCOPE-2.1/2.2:** `app.records.criteria` maps criteria-chunk field text
    onto patient-record feature paths via a curated synonym map (never
    inferred), mirroring the existing abbreviation-expansion pattern
    (DEVIATIONS #71). Missing-info is released as reported content, not a
    HITL hold (DEVIATIONS #76) — a real, ARCH-text-driven correction found
    while implementing the Phase-1-committed `RELEASE_POLICY` table's literal
    reading.
  - **Memory:** `app.memory.conversation`/`patient_context`/`checkpointer`
    all implemented; conversation/patient_context verified against real
    Postgres (AES-256-GCM round trip, cross-conversation replay rejected via
    AAD binding); the real LangGraph `PostgresSaver` checkpointer needed
    three fixes only a real-Postgres run could surface (DSN format, DDL
    privilege, target schema — DEVIATIONS #82).
  - **HITL:** full accept axis (`app.hitl.decisions.apply_decision`) and
    escalation lifecycle (`app.hitl.escalation`) implemented and verified
    end-to-end against real Postgres, including reject-path
    `patient_context` rollback.
  - **Multi-rater rubric workflow:** `app.rubric.workflow` implements the
    full state machine (rate -> open queue -> >=3 distinct raters -> IRR ->
    archive); `app.rubric.irr` implements Krippendorff's alpha (ordinal).
    Real-Postgres verification found and fixed two genuine bugs no offline
    fake-session test could reach: `scripts/seed_db.py` was still a
    print-only stub, leaving `eval.rubric_domain` empty and every rating
    insert failing its FK constraint; Krippendorff's alpha crashed on a
    unanimous single-item rating (DEVIATIONS #81).
  - **Eval harness:** `app.eval.harness.run_harness` runs the real compiled
    graph over the fixed test set, computes retrieval/citation/
    expected-outcome/scope-safety metrics against `Settings`-pinned
    thresholds, and gates (`EvalGateFailure`) on breach; `app.eval.tasks`
    closes the Phase-2-flagged gap of persisting generated questions as
    `eval_question` rows.
  - **Routes:** `/query`, `/hitl/*`, `/rubric/*`, `/review-queue/*`,
    `/eval/*`, `/conversations/*` all implemented (previously 501 stubs).
  - **Real-infrastructure verification** (ephemeral Postgres + Redis, torn
    down after): conversation/patient_context/escalation/HITL-decision
    lifecycle, the audit hash chain and its append-only trigger (rejects
    UPDATE even for the table-owning role), the rubric workflow through
    archival, the real LangGraph Postgres checkpointer, real Celery task
    enqueueing for all 4 new task bodies, and a full HTTP round trip through
    the live FastAPI app for a SCOPE-2.3 query — all verified working, with
    3 real bugs found and fixed along the way (DEVIATIONS #81-82) that no
    offline mock could have caught.
  - Rows updated: PRD-020..024, PRD-030..033, PRD-040..048, PRD-050..056,
    PRD-066, PRD-070..073, PRD-085, PRD-087, PRD-088, PRD-105, PRD-NFR-2.
  - **394 passing offline tests** (was 233 at Checkpoint 2).

  **This closes out the Phase 3 checklist** (`prompt.txt`): the agent
  topology, persistent memory, the three HITL modes + escalation triggers,
  the full multi-rater rubric evaluation workflow, and the eval harness are
  all implemented and tested. Deferred, documented items: secondary IRR
  stats (DEVIATIONS #77), `eval.result` row creation from a live
  answer/harness run (DEVIATIONS #79), rubric-rating audit events
  (DEVIATIONS #80), and the LangGraph checkpoint msgpack type-registration
  warning (DEVIATIONS #83). Ready for Checkpoint 3 review.
