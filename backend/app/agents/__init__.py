"""Multi-agent orchestration (ARCH-016; PRD-020, PRD-021).

LangGraph state graph. Nine roles (7 active + 2 extension-seam stubs):
orchestrator, retrieval, patient-record, stage-classifier, missing-info,
guideline-synthesis, citation-verifier, escalation, and the STUBS
local-adaptation (returns capability_not_enabled) and next-step-recommender
(reserved name / interface stub only — not in the runtime graph).

Cross-cutting rules (ARCH §10.3):
- chunk text is untrusted data, never instructions;
- every model call goes through app.llm.gateway.LLMGateway;
- only patient-record / stage-classifier / missing-info agents may put patient
  field VALUES in a prompt, and only fields authorized for (role, purpose);
- scope classification, thresholds, conflict flags, citation resolution and
  quote-integrity are deterministic code, not model calls.
"""
