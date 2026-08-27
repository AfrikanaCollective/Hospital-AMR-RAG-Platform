-- Hospital RAG Platform — schema + role bootstrap (ARCH-008 / ARCH-035 / PRD-085).
-- Runs once on first postgres container start (docker-entrypoint-initdb.d).
--
-- Key property: the application role can INSERT and SELECT audit rows but has
-- NO UPDATE/DELETE on the audit schema — the audit log is append-only.

\connect hospital_rag

-- ── schemas (ARCH-008) ──────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS corpus;   -- guideline documents, versions, chunks
CREATE SCHEMA IF NOT EXISTS records;  -- patient records (PHI)
CREATE SCHEMA IF NOT EXISTS memory;   -- conversations, messages, patient_context, checkpoints
CREATE SCHEMA IF NOT EXISTS hitl;     -- escalations, decisions
CREATE SCHEMA IF NOT EXISTS eval;     -- questions, results, rubric, ratings, IRR, archive
CREATE SCHEMA IF NOT EXISTS audit;    -- append-only audit_event
CREATE SCHEMA IF NOT EXISTS iam;      -- users, roles, sessions, field policy

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- envelope encryption helpers (ARCH-032)

-- ── application role ────────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hrag_app') THEN
    CREATE ROLE hrag_app LOGIN PASSWORD 'hrag_app_pw';
  END IF;
END $$;

GRANT USAGE ON SCHEMA corpus, records, memory, hitl, eval, audit, iam TO hrag_app;

-- Full DML on the operational schemas.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA
  corpus, records, memory, hitl, eval, iam TO hrag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA corpus, records, memory, hitl, eval, iam
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hrag_app;

-- Audit schema: append-only. INSERT + SELECT only, no UPDATE/DELETE, ever.
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA audit TO hrag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
  GRANT SELECT, INSERT ON TABLES TO hrag_app;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM hrag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
  REVOKE UPDATE, DELETE, TRUNCATE ON TABLES FROM hrag_app;

-- Sequences (for bigserial audit id etc.).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA
  corpus, records, memory, hitl, eval, audit, iam TO hrag_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA corpus, records, memory, hitl, eval, audit, iam
  GRANT USAGE, SELECT ON SEQUENCES TO hrag_app;

-- Row-level security is enabled per-table by the Alembic migrations for
-- records.* and memory.patient_context (ARCH-034); policies are keyed off a
-- session GUC set by the API request context (app.current_patient_scope).
