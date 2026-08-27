<!-- Prompt template: orchestrator scope classification (ARCH-025). Version v1. Draft. -->
<!-- Backed by a deterministic lexical backstop in app/scope/classifier.py. -->

# Task

Classify the QUERY into exactly one label:

- `scope_1` — asks what a guideline says / recommends for a described
  presentation (hypothetical or general). Reporting/synthesis of guideline
  content.
- `scope_2_stage` — asks to classify a specific patient's CURRENT stage of care.
- `scope_2_missing_info` — asks what information is missing for a specific
  patient relative to a guideline.
- `scope_2_excluded` — asks for **what should happen next** for a specific
  patient (synthesising patient data + guidelines into a directive), OR asks to
  **adjust/substitute** a guideline recommendation for a local operational
  constraint. These are NEVER answered.
- `out_of_scope` — cohort/population questions, non-clinical, or anything else.

When uncertain between `scope_2_excluded` and anything else, choose
`scope_2_excluded`. When uncertain between `out_of_scope` and a scope label,
choose `out_of_scope`. Do not answer the query.

Output: `{"label": "<one of the above>", "reason": "<short>"}`

QUERY:
{{query}}

PATIENT ATTACHED: {{has_patient}}
