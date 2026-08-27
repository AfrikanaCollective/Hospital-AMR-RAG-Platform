# CDS-FUTURE.md — Explicitly Excluded Capabilities

**Status:** Phase 0. Last updated 2026-08-27.
**Related:** [PRD.md](PRD.md) (PRD-053, PRD-054, PRD-055, PRD-056, PRD-NG-002,
PRD-NG-003) · [ARCHITECTURE.md](ARCHITECTURE.md) §9 (SCOPE-2.3, SCOPE-2.4,
SCOPE-2.5, ARCH-026) · [ARCHITECTURE-ESSENTIALS.md](ARCHITECTURE-ESSENTIALS.md) §4.

---

## Purpose of this file

This system sits deliberately **on the retrieval/reporting side** of the line
that separates "surfacing and citing source material" from "clinical decision
support (CDS) proper". Two capabilities that live on the far side of that line
are **excluded from this build**. This file records:

1. what they are,
2. why they are excluded from the MVP,
3. what would have to be true before they could be built,
4. the relationship (a narrow one) between the in-scope evaluation evidence and
   any future review of these capabilities,
5. the extension seam left in the architecture so they could be added later
   without a redesign.

**The boundary in this file is hard.** Per the build's general working rules:
if any later phase's implementation appears to require one of these
capabilities to function, **stop and flag it** — do not implement a workaround,
a partial version, or a "temporary" heuristic.

---

## Excluded capability 1 — Autonomous next-step recommendation from patient data

**ID:** SCOPE-2.3 · **PRD:** PRD-053, PRD-NG-002

### What it is

Generating a suggestion of **"what should happen next"** for a specific patient
(even a synthetic one) by **synthesizing the patient's data together with
guideline content**, going beyond simply reporting matched guideline text.

Examples of what is **excluded**:
- "Given this patient's eGFR and the guideline, the next step is to switch to
  agent B."
- "This patient meets criteria for escalation to the HDU."
- "Start antibiotic X at dose Y for this patient."
- Ranking or prioritising candidate next actions *for this patient*.

Examples of what remains **in scope** (for contrast — see ARCHITECTURE.md §9.2):
- Reporting, with citations, what a retrieved guideline says for a presentation
  matching the described features (SCOPE-1.1), framed as "Guideline X
  recommends…".
- Classifying the patient's **current** stage of care against **extractable,
  cited criteria** (SCOPE-2.1) — a grounded classification, not a
  recommendation about the future.
- Identifying and requesting **missing information** the matched guideline
  requires (SCOPE-2.2).

The distinction: in-scope outputs report *what a source says* or classify
*what is currently true* against cited criteria. The excluded capability
produces a *new directive conclusion about what to do*, which is the model's
synthesis rather than a retrievable fact.

### Why it is excluded from the MVP

- It crosses from retrieval/reporting into **clinical decision support
  proper**. That raises real regulatory questions — e.g. FDA / EU-MDR-style
  **software-as-a-medical-device (SaMD) classification**, the need for
  **clinical validation**, and **liability review** — which are **product and
  legal decisions, not engineering ones**, and have not been made.
- Patient-specific directive output cannot be grounded the way guideline
  reporting can: the "next step" is frequently *not* a verbatim retrievable
  statement, so the enforced-grounding guarantee (constraint #4) would not
  hold.
- The safety/disclaimer posture of the MVP ("reports and cites source material
  only", "defers clinical judgement to the human user") is incompatible with
  emitting directive per-patient conclusions.

### What would need to be true before it could be built

- A completed **regulatory classification** for the intended use and market,
  and a decision by product + legal to proceed on that basis.
- A **clinical governance** structure signed off (clinical safety officer /
  equivalent, hazard log, clinical risk management file).
- A **prospective clinical validation strategy** with predefined endpoints,
  a reference standard, and acceptance thresholds — not retrospective
  self-scoring.
- A defined **liability and human-factors** model (how the output is presented,
  what the clinician is accountable for, override/feedback paths).
- A grounding/uncertainty approach that is defensible for **non-verbatim**
  conclusions (e.g. explicit reasoning traces tied to cited criteria, calibrated
  confidence, mandatory human confirmation).
- Post-market surveillance and audit design.

Until all of the above exist, this capability is not to be implemented.

---

## Excluded capability 2 — Guideline adjustment based on local operational constraints

**ID:** SCOPE-2.4 · **PRD:** PRD-054, PRD-NG-003

### What it is

Automatically **substituting or modifying** a guideline recommendation because
of a **local operational constraint** — a service is unavailable, a drug is out
of stock, a scan cannot be done today — **when that substitution is not itself
explicitly present in the source guideline text**.

Examples of what is **excluded**:
- "Drug A is out of stock, so use drug C instead" — where drug C is *not*
  named in the retrieved guideline.
- "MRI is unavailable, so the equivalent step is CT" — where the guideline does
  not state that equivalence.
- Any inference that reasons *from* a constraint *to* a clinically different
  plan.

What remains **in scope** — the **narrow exception, SCOPE-2.5**:
- If the local constraint coincides with an alternative **already stated in the
  retrieved guideline text itself** (e.g. the guideline explicitly lists a
  documented second-line option, or an "if X is unavailable, Y" clause), the
  system **may surface that alternative as reported guideline content, with a
  citation**. It is still *reporting what the source says*, not reasoning to a
  substitution.
- If a local constraint has **no** such documented alternative in the retrieved
  text, the system **routes to HITL escalation**
  (`trigger_code = local_constraint_no_source_alt`) — it does **not** generate
  a substitution.

### Why it is excluded from the MVP

- Ad hoc substitution is a **clinical substitution judgement**, not a
  retrieval task. Hospitals deliberately route these decisions through
  **formal processes** — pharmacy and antimicrobial stewardship sign-off,
  therapeutics committees — precisely because informal substitution reasoning
  is a **known, well-documented source of error** (wrong-drug, wrong-dose,
  interaction, contraindication).
- The substitution conclusion is, by definition, **not in the source text**,
  so it cannot satisfy enforced grounding (constraint #4).
- It shares the same regulatory/SaMD and liability exposure as excluded
  capability 1.

### What would need to be true before it could be built

- The same regulatory classification, clinical governance sign-off, validation
  strategy, and liability model as excluded capability 1.
- Integration with the hospital's **formal substitution governance** (e.g. an
  approved formulary-substitution ruleset with pharmacy ownership), so the
  system surfaces *pre-approved* substitutions rather than inventing them —
  which is arguably a different, rules-based product, not model reasoning.
- A safety case specifically covering interaction/contraindication/dose
  consequences of substitution.

Until then, only the SCOPE-2.5 narrow exception (report a documented
alternative already in a retrieved source; otherwise escalate) is permitted.

---

## Relationship to the in-scope multi-rater rubric / IRR evidence

The MVP runs a structured multi-rater rubric + inter-rater reliability workflow
(ARCHITECTURE.md §14) over its **in-scope** outputs (SCOPE-1.*, SCOPE-2.1,
SCOPE-2.2).

**That evidence is, at most, a *prerequisite input* to a future review of the
excluded capabilities — nothing more.** Specifically:

- It demonstrates that **a measurement process exists** — a defined rubric,
  multiple independent clinician raters, an IRR statistic, an audit trail, and
  the ability to separate auto-generated from clinician-submitted results.
- It does **not** demonstrate that SCOPE-2.3 or SCOPE-2.4 are **safe**,
  **valid**, or **ready to build**.
- **Strong in-scope evaluation results MUST NOT be treated as justification**
  for unlocking the excluded capabilities. Those would require their **own
  separate validation pathway** — new endpoints, a new reference standard,
  prospective evaluation, and the regulatory/governance steps listed above —
  regardless of how good the in-scope numbers look.
- Any report that uses the rubric/IRR data must state this limitation
  explicitly (PRD-048).

---

## Extension seam left in the architecture (ARCH-026)

So these capabilities can be added later **without a redesign**, the
architecture leaves:

- **`local-adaptation agent`** — a **named agent role present in the LangGraph
  definition** with a typed interface
  (`propose_local_adaptation(context) -> AdaptationResult`) whose body is
  **not implemented**: it raises `NotImplementedError` and instead returns a
  fixed escalation (`trigger_code = capability_not_enabled`).
- **`next-step-recommender`** — a **reserved role name with an interface stub
  only**, not wired into the runtime graph, marking where SCOPE-2.3 would
  attach.
- **`LOCAL_ADAPTATION_ENABLED`** — a feature flag that is **hard-wired to
  `false`**. Flipping it does nothing without implementing the agent body; the
  code comment at the flag points here.
- Clear `# CDS-FUTURE / DO NOT IMPLEMENT WITHOUT GOVERNANCE GATE` markers at
  each stub.

**None of these stubs contain any recommendation or substitution logic.** They
exist only so that a future, separately-governed project has a defined place to
plug in.
