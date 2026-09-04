---
# Operator attestation (ARCH-039 / DEVIATIONS #33). Every field below must be
# filled with real values before `scripts.ingest_deidentified_records` will run.
# Replace every TODO_CONFIRM.
source: "The Clinical Information Network (CIN)"
collection_period: "2021-01-01 to 2024-12-31"
site: "Newborn units of the CIN hospitals"
deidentification_method: "Removal of direct identifiers, inclusion of integer surrogate key"
deidentification_standard: "Local IRB-approved de-identification"
consent_basis: "Waiver of consent under IRB approval #SERU3 / broad consent / other"
licence: "CC BY-NC-SA 4.0"
attested_by: "Timothy Tuti - Primary Investigator"
attested_date: "2026-09-01"
---

# Dataset: newborn_nbu_2021

De-identified / anonymised newborn dataset supplied by the operator for
development of the Hospital RAG Platform. Ingested via
`scripts/ingest_deidentified_records.py` using `field_mapping.yaml`.

**This is real patient-derived data.** It is handled as PHI end to end:
envelope-encrypted at rest, field-level RBAC + RLS, purpose-of-use, full audit,
never leaves the deployment, never used for training. It is **not** committed to
version control (`.gitignore`).

## Shape

- Format: EAV / long — columns `key, field_name, field_value, context`.
- ~40,871 patients, one assessment snapshot each; `(key, field_name)` is unique.
- `key` is an integer surrogate id (no name / MRN in the source).

## Known residual identifiers

- `admission_date_time` is retained as a full timestamp (C3, DEVIATIONS #36).
  It is kept for `day_of_life` reconstruction, vitals timestamping, and
  ordering, and is protected like every other field. If your de-identification
  basis requires date shifting or generalisation, add a `date_shift` /
  `generalise_month` transform for `admission_date_time` in `field_mapping.yaml`
  and re-ingest.

## Source variables (32) by context

| context | variables                                                                                                                                        |
|---|--------------------------------------------------------------------------------------------------------------------------------------------------|
| demographics | age_days, birth_weight (kg), gestational_age (weeks), sex, weight_now (kg)                                                                       |
| encounter_details | admission_date_time, care_setting (all "NBU"), triage_category (all "None")                                                                      |
| vitals | capillary_refill (1–7 s), heart_rate, oxygen_saturation, respiratory_rate, temparature *(sic — °C)*                                              |
| history_examination | apnoea, bulging_fontanelle, central_cyanosis, convulsions, crackles, difficulty_feeding, floppy, grunting, indrawing, irritable (all TRUE/FALSE) |
| interventions | antibiotics, cpap, feeds, fluids, kmc, oxygen, phenobarbital (all TRUE/FALSE)                                                                    |
| medication | ampicillin, ceftazidime, ceftriaxone, gentamicin, penicillin (all TRUE/FALSE)                                                                    |

## Mapping

See `field_mapping.yaml`. Transforms of note: `birth_weight`/`weight_now`
kg→g; `sex` normalised to `male`/`female`; `triage_category` literal `"None"`
→ null; `temparature` misspelling mapped to `temperature_c`; the 22 boolean
sign/intervention/medication variables expand into
`examination_findings[]` / `interventions[]` / `medications[]`.
`date_of_birth` is derived (`admitted_at − age_days`, approximate).

## Limitations

- Single snapshot per patient (no trends).
- `care_setting` and `triage_category` are constant in this extract.
- Many fields are partially populated — this is expected and exercises the
  SCOPE-2.2 missing-information path.
