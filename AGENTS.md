# AGENTS.md

This file exists for tools and contributors that look for `AGENTS.md`.

**All agent working instructions for this repository live in
[CLAUDE.md](CLAUDE.md).** That includes:

- the phase-checkpoint protocol (hard stops between phases 0–5),
- the non-negotiable rules (no real PHI; no independent clinical advice;
  enforced grounding; the hard `CDS-FUTURE.md` boundary; no hardcoded model
  names; append-only audit; PHI never leaves the deployment),
- code conventions (Python/ruff/mypy, FastAPI, SQLAlchemy-per-schema, Pydantic
  v2, React/Vite/TS),
- how to reference requirement IDs (`PRD-###`, `ARCH-###`, `SCOPE-#.#`),
- testing expectations and the gating safety tests,
- which docs must be kept in sync with every change
  (README.md, TRACEABILITY.md, ARCHITECTURE-ESSENTIALS.md, DEVIATIONS.md).

Do not duplicate that content here — read [CLAUDE.md](CLAUDE.md).

Document map: [README.md](README.md) · [PRD.md](PRD.md) ·
[ARCHITECTURE.md](ARCHITECTURE.md) ·
[ARCHITECTURE-ESSENTIALS.md](ARCHITECTURE-ESSENTIALS.md) ·
[CDS-FUTURE.md](CDS-FUTURE.md) · [TRACEABILITY.md](TRACEABILITY.md) ·
[DEVIATIONS.md](DEVIATIONS.md)
