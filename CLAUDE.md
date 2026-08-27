# CLAUDE.md — How to work in this repository

Instructions for any coding agent (including future sessions of yourself)
working on the Hospital RAG Platform. Read this before touching code.

---

## 1. What this project is

A Retrieval-Augmented Generation platform for hospital use: grounded, **cited**
answers over clinical guideline documents, plus non-directive structured
inference from synthetic patient records, with a multi-agent orchestration
layer, persistent memory, HITL escalation, and a multi-rater evaluation
workflow.

Read in this order:
1. **[ARCHITECTURE-ESSENTIALS.md](ARCHITECTURE-ESSENTIALS.md)** — the
   short-form critical-decisions doc. Start here every session.
2. **[PRD.md](PRD.md)** — requirements (`PRD-###`), non-goals (`PRD-NG-###`).
3. **[ARCHITECTURE.md](ARCHITECTURE.md)** — full design (`ARCH-###`,
   `SCOPE-#.#`). Only load the section you need.
4. **[CDS-FUTURE.md](CDS-FUTURE.md)** — the two excluded capabilities. The
   boundary here is **hard**.
5. **[TRACEABILITY.md](TRACEABILITY.md)** — requirement → file → test → status.
6. **[DEVIATIONS.md](DEVIATIONS.md)** — every judgment call. Append-only.
7. **[README.md](README.md)** — setup, run, current phase status.

---

## 2. The phase-checkpoint protocol (hard rule)

The build runs in phases 0–5 (see `prompt.txt`). **Each phase ends at a
checkpoint where the user reviews and must explicitly approve before the next
phase begins.** Never start the next phase without that approval. Never chain
phases in one pass.

Current phase status is in [README.md](README.md) §Status.

If a requirement in `prompt.txt` conflicts with something you discover during
implementation (library limitation, etc.), **stop and flag it** — do not
quietly work around it.

---

## 3. Non-negotiable rules

These come from the build constraints (PRD-C1…C8) and are enforced by tests.

1. **No real PHI, ever.** All data is synthetic and project-generated. Every
   patient-record field is PHI by default. Never ask for, accept, invent, or
   commit real patient data.
2. **No independent clinical advice.** The system *reports and cites* retrieved
   source text. Wording is "Guideline X recommends…", never "You should…".
   Every response carries a non-removable disclaimer. This is enforced in agent
   **prompt templates** (`backend/app/agents/prompts/`) and by the deterministic
   wording filter (`backend/app/grounding/wording.py`) — both, not either.
3. **Grounding is enforced.** No answer segment ships unless a citation
   resolves to a chunk that was in *that turn's* retrieval snapshot and its
   verbatim quote supports the claim. Low confidence / conflicting sources / no
   match ⇒ "no guideline found" or HITL escalation — **never** a
   general-knowledge answer.
4. **The CDS boundary is hard.** `SCOPE-2.3` (autonomous next-step
   recommendation from patient data) and `SCOPE-2.4` (guideline adjustment for
   local operational constraints not in source text) are **not implemented,
   even partially**. If a task appears to require them, **stop and flag**. The
   only permitted extension points are the named stubs
   (`local_adaptation_agent.py`, `next_step_recommender.py`) which contain no
   logic. Do not add logic to them.
5. **No hardcoded model names.** `MODEL_ID`, `EMBEDDING_MODEL_ID`,
   `RERANKER_MODEL_ID` come from config (`backend/app/config.py`) with
   placeholder defaults. If a model name cannot be verified against current
   gateway documentation, flag it (`MODEL_ID_VERIFIED=false` logs a warning;
   the placeholder blocks the answer path). Never guess a model id in code.
6. **Audit is append-only.** `audit.audit_event` has no `UPDATE`/`DELETE` grant
   for the app role. Never write a migration or query that alters historical
   audit rows.
7. **PHI never leaves the deployment.** Model calls go only to the configured
   self-hosted gateway. No PHI in logs (the logger redacts), telemetry, or
   training.

---

## 4. Conventions

### Layout
```
backend/app/        FastAPI app, agents, retrieval, grounding, ingestion, rubric, eval
backend/app/db/models/   SQLAlchemy models, one file per Postgres schema
backend/app/schemas/     Pydantic request/response models
backend/app/api/routes/  endpoint modules
backend/scripts/    synthetic data generator, sample-guideline fetch, db seed
backend/tests/      pytest
frontend/src/       React (Vite + TS)
deploy/             nginx, postgres init SQL
data/               record_schema.json, generated synthetic data, sample guidelines
```

### Python
- Target 3.11+. Formatter/linter: **ruff** (`ruff format`, `ruff check`).
  Types: **mypy** (`make typecheck`). Keep new code typed.
- FastAPI: routes thin; logic in service modules. Dependencies (auth, RBAC,
  purpose-of-use, DB session) via `backend/app/api/deps.py`.
- DB: SQLAlchemy 2.0 style, models grouped by schema module. Migrations via
  Alembic (`backend/alembic/`). Schemas + roles are created by
  `deploy/postgres/init/01_schemas_roles.sql`.
- Pydantic v2 for all API and config models.
- Determinism where it matters: scope classification, confidence thresholds,
  conflict flags, citation resolution, and quote-integrity are **plain code**,
  not model calls. Only synthesis, entailment judgement, and narrative
  generation call the LLM.
- Every model call goes through `backend/app/llm/gateway.py:LLMGateway`. Agents
  never name a model.

### TypeScript / React
- Vite + TS. API client in `frontend/src/api/client.ts`; shared types in
  `frontend/src/types.ts` (kept aligned with the backend OpenAPI schema).
- The disclaimer banner (`DisclaimerBanner.tsx`) is always mounted on any view
  that shows an answer.

### Requirement IDs in code
- Reference the relevant `PRD-###` / `ARCH-###` / `SCOPE-#.#` in the module
  docstring or near the implementing code, and in the test that covers it.
- Reference IDs in commit messages ("Implement hybrid retrieval (ARCH-003,
  PRD-010)").

### Commits
- Work on a branch, not `main`/`master`. Commit/push only when the user asks.
- End commit messages with:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01RKWpajeQiH8dzCtfxqd2Tm
  ```

---

## 5. Testing expectations

- **pytest** in `backend/tests/`. Run `make test`.
- Any requirement you implement gets at least one test, and its
  `TRACEABILITY.md` row is updated (status + implementing file + test) **in the
  same change**.
- **Gating safety tests must always pass** (they fail the build otherwise):
  - `test_scope_boundary.py` — SCOPE-2.3/2.4-style prompts produce
    `outcome = escalated`, `trigger_code = scope_boundary`, **zero**
    recommendation content.
  - grounding: `no_guideline_expected` cases return explicit "no guideline
    found" with zero recommendation (100%).
  - `disclaimer_present_rate` == 100%.
  - `test_audit_append_only.py` — no UPDATE/DELETE path to audit rows.
  - `test_patient_context_rejects_recommendations.py` — repo layer rejects
    recommendation-shaped memory writes.
- Unit tests must not require network. The `llm-gateway` `stub` profile and
  fixture fakes cover model/embedding/rerank calls offline.

---

## 6. Docs you must keep current (treat staleness as a defect)

- **README.md** — any change that adds/removes/alters functionality (new
  endpoint, new env var, new setup step, changed run instructions, phase
  status) updates README.md in the *same* change.
- **TRACEABILITY.md** — any time work starts or completes on a requirement,
  update that row (status + file(s) + test(s)) in the *same* change.
- **ARCHITECTURE-ESSENTIALS.md** — keep in sync whenever ARCHITECTURE.md
  changes.
- **DEVIATIONS.md** — append an entry the *moment* a judgment call is made (an
  ambiguous requirement interpreted, an undecided edge case handled, a default
  chosen where the spec was silent). Never edit or delete past entries. When in
  doubt, log it.

---

## 7. Secrets & safety

- `.env` is gitignored. Never commit secrets, keys, or `.env`. `.env.example`
  is the committed template.
- `SECRETS_BACKEND` (default `file`) supplies the crypto KEK. The dev key logs
  a loud "DEV KEY — not for real data" line; that is expected in dev, and a
  signal that this deployment must not touch real data.
- The synthetic record generator marks its output with
  `dataset_provenance: "synthetic-generator-v1"`; the ingestion real-data
  heuristic (`backend/app/ingestion/records.py`) whitelists that marker so the
  project's own synthetic data is accepted while unmarked "real-looking"
  batches are rejected (see DEVIATIONS.md #21).
