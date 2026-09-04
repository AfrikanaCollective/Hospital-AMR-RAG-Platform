"""Synthetic patient-record generator (PRD-006, PRD-081; ARCH §5.2).

Produces SYNTHETIC-ONLY patient records as JSON (one array) and CSV (one flat
row per record). Deterministic given --seed. Output is marked with
`dataset_provenance = "synthetic-generator-v1"` so ingestion's real-data
heuristic accepts it (DEVIATIONS.md #21).

`--domain` / `RECORD_DOMAIN` selects the clinical content library and **must
match the ingested guideline corpus's domain** (DEVIATIONS.md #30):

  - `neonatal`        (default) — matches the bundled dev corpus (WHO newborn
                       health 2017, WHO SBI in young infants 0-59 days 2024,
                       Kenya MOH Comprehensive Newborn Care Protocols 2022)
  - `adult_inpatient` — the original Phase-1 library, retained

The record *schema* is domain-agnostic; only the *content* (problems, meds +
weight-based dosing, vitals ranges, care settings) is per-domain.

A configurable fraction of records is deliberately SPARSE (fields nulled) to
support hard-case ("missing_info_expected") question generation (PRD-064).

Usage:
    python -m scripts.generate_synthetic_records --count 200 --domain neonatal \
        --out ../data/patient_records/synthetic
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

try:
    from faker import Faker
except ImportError:  # pragma: no cover - dev dependency
    Faker = None  # type: ignore[assignment]

from app.schemas.record import (
    SCHEMA_VERSION,
    SYNTHETIC_PROVENANCE,
    Encounter,
    LabResult,
    Medication,
    PatientRecord,
    Vitals,
)


@dataclass(frozen=True)
class DomainLib:
    name: str
    care_settings: list[str]
    complaints: list[str]
    problems: list[str]
    # (name, dose, route, frequency)
    drugs: list[tuple[str, str, str, str]]
    # (analyte, unit, lo, hi, ref_lo, ref_hi)
    labs: list[tuple[str, str, float, float, float, float]]
    dob_min_days: int
    dob_max_days: int
    neonatal: bool = False
    extras: dict = field(default_factory=dict)


NEONATAL = DomainLib(
    name="neonatal",
    care_settings=[
        "Newborn Unit", "Kangaroo Mother Care ward", "Nursery", "Special Care Nursery",
        "Postnatal ward", "Labour ward",
    ],
    complaints=[
        "difficulty breathing", "not feeding well", "lethargy", "fever",
        "hypothermia", "jaundice", "convulsions", "grunting", "poor cry",
        "abdominal distension", "apnoea",
    ],
    problems=[
        "prematurity", "low birth weight", "neonatal jaundice",
        "respiratory distress syndrome", "birth asphyxia", "hypoxic-ischaemic encephalopathy",
        "possible serious bacterial infection", "neonatal sepsis", "hypoglycaemia",
        "hypothermia", "feeding difficulty",
    ],
    drugs=[
        ("benzylpenicillin", "50000 IU/kg", "IV", "12-hourly"),
        ("gentamicin", "5 mg/kg", "IV", "24-hourly"),
        ("ampicillin", "50 mg/kg", "IV", "12-hourly"),
        ("phenobarbitone", "20 mg/kg", "IV", "loading dose"),
        ("caffeine citrate", "10 mg/kg", "oral", "24-hourly"),
        ("vitamin K", "1 mg", "IM", "once"),
        ("10% dextrose", "2 mL/kg", "IV", "bolus"),
    ],
    labs=[
        ("blood glucose", "mmol/L", 1.0, 8.0, 2.6, 6.0),
        ("total bilirubin", "umol/L", 20, 450, 0, 200),
        ("C-reactive protein", "mg/L", 1, 200, 0, 5),
        ("white cell count", "10^9/L", 2.0, 40.0, 9.0, 30.0),
        ("haemoglobin", "g/L", 90, 220, 135, 200),
    ],
    dob_min_days=0,
    dob_max_days=59,
    neonatal=True,
)

ADULT_INPATIENT = DomainLib(
    name="adult_inpatient",
    care_settings=["ED", "general ward", "HDU", "ICU", "surgical ward", "medical ward"],
    complaints=[
        "shortness of breath", "chest pain", "fever and cough", "abdominal pain",
        "confusion", "fall", "vomiting", "reduced urine output", "leg swelling",
        "headache", "back pain", "palpitations",
    ],
    problems=[
        "type 2 diabetes mellitus", "hypertension", "chronic kidney disease stage 3",
        "atrial fibrillation", "COPD", "heart failure", "asthma", "ischaemic heart disease",
    ],
    drugs=[
        ("amoxicillin", "500 mg", "oral", "TDS"),
        ("furosemide", "40 mg", "IV", "OD"),
        ("metformin", "1 g", "oral", "BD"),
        ("apixaban", "5 mg", "oral", "BD"),
        ("paracetamol", "1 g", "oral", "QDS"),
        ("salbutamol", "5 mg", "neb", "PRN"),
    ],
    labs=[
        ("creatinine", "umol/L", 50, 350, 60, 110),
        ("potassium", "mmol/L", 2.8, 6.5, 3.5, 5.3),
        ("haemoglobin", "g/L", 70, 175, 120, 165),
        ("white cell count", "10^9/L", 2.0, 25.0, 4.0, 11.0),
        ("C-reactive protein", "mg/L", 1, 350, 0, 5),
        ("lactate", "mmol/L", 0.4, 8.0, 0.5, 2.0),
    ],
    dob_min_days=365 * 18,
    dob_max_days=365 * 95,
)

DOMAIN_LIBS: dict[str, DomainLib] = {NEONATAL.name: NEONATAL, ADULT_INPATIENT.name: ADULT_INPATIENT}
DEFAULT_DOMAIN = os.environ.get("RECORD_DOMAIN", "neonatal")


def _neonatal_vitals(rng: random.Random, at: datetime, birth_weight_g: float, dol: int) -> Vitals:
    return Vitals(
        recorded_at=at,
        heart_rate_bpm=rng.randint(90, 190),
        resp_rate_bpm=rng.randint(25, 75),
        mean_bp_mmhg=rng.randint(28, 55),
        temperature_c=round(rng.uniform(35.0, 38.5), 1),
        spo2_percent=rng.randint(80, 100),
        weight_g=round(birth_weight_g + dol * rng.uniform(-10, 30), 0),
    )


def _adult_vitals(rng: random.Random, at: datetime) -> Vitals:
    return Vitals(
        recorded_at=at,
        heart_rate_bpm=rng.randint(50, 130),
        resp_rate_bpm=rng.randint(10, 34),
        systolic_bp_mmhg=rng.randint(80, 180),
        diastolic_bp_mmhg=rng.randint(45, 105),
        temperature_c=round(rng.uniform(35.5, 39.8), 1),
        spo2_percent=rng.randint(85, 100),
    )


def _mk_record(rng: random.Random, fake: object, idx: int, sparse: bool, lib: DomainLib) -> PatientRecord:
    admitted = datetime.now(UTC) - timedelta(hours=rng.randint(2, 240))
    given = fake.first_name() if fake else f"Synth{idx:04d}"
    family = fake.last_name() if fake else f"Patient{idx:04d}"

    dob = None if sparse and rng.random() < 0.3 else (
        datetime.now(UTC).date()
        - timedelta(days=rng.randint(lib.dob_min_days, lib.dob_max_days))
    )

    ga_weeks = birth_weight_g = dol = None
    if lib.neonatal:
        dol = (datetime.now(UTC).date() - dob).days if dob else rng.randint(0, 28)
        ga_weeks = None if sparse and rng.random() < 0.4 else round(rng.uniform(26.0, 41.5), 1)
        birth_weight_g = None if sparse and rng.random() < 0.4 else float(rng.randint(650, 4200))

    n_vitals = 0 if sparse and rng.random() < 0.5 else rng.randint(1, 4)
    vitals: list[Vitals] = []
    for h in range(n_vitals):
        at = admitted + timedelta(hours=h * 6)
        if lib.neonatal:
            vitals.append(_neonatal_vitals(rng, at, birth_weight_g or 3000.0, (dol or 0) + h // 4))
        else:
            vitals.append(_adult_vitals(rng, at))

    n_labs = 0 if sparse and rng.random() < 0.6 else rng.randint(1, 5)
    labs: list[LabResult] = []
    for analyte, unit, lo, hi, rlo, rhi in rng.sample(lib.labs, k=min(n_labs, len(lib.labs))):
        labs.append(
            LabResult(
                analyte=analyte,
                value=round(rng.uniform(lo, hi), 2),
                unit=unit,
                collected_at=admitted + timedelta(hours=rng.randint(0, 48)),
                reference_low=rlo,
                reference_high=rhi,
            )
        )

    meds = [
        Medication(name=n, dose=d, route=r, frequency=f, started_at=admitted, active=True)
        for (n, d, r, f) in rng.sample(lib.drugs, k=0 if sparse else rng.randint(0, 4))
    ]

    return PatientRecord(
        schema_version=SCHEMA_VERSION,
        dataset_provenance=SYNTHETIC_PROVENANCE,
        record_id=f"SYNREC-{idx:06d}",
        mrn=f"SYN-{idx:08d}",
        given_name=given,
        family_name=family,
        date_of_birth=dob,
        sex=rng.choice(["female", "male", "unknown"]),
        encounter=Encounter(
            admitted_at=admitted,
            ward=None if sparse else rng.choice(["NBU-A", "NBU-B", "KMC", "4A", "6C", "AMU"]),
            care_setting=None if sparse and rng.random() < 0.4 else rng.choice(lib.care_settings),
            presenting_complaint=None if sparse and rng.random() < 0.2 else rng.choice(lib.complaints),
            triage_category=None if sparse else str(rng.randint(1, 5)),
            gestational_age_weeks=ga_weeks,
            birth_weight_g=birth_weight_g,
            day_of_life=dol if lib.neonatal else None,
        ),
        problems=[] if sparse else rng.sample(lib.problems, k=rng.randint(0, 3)),
        allergies=[] if rng.random() < 0.85 else ["penicillin"],
        medications=meds,
        vitals=vitals,
        labs=labs,
        clinical_notes=None if sparse
        else f"Synthetic {lib.name} note: presented with {rng.choice(lib.complaints)}; for review.",
        consent_flags={"research_opt_out": rng.random() < 0.1},
    )


def generate(
    count: int,
    seed: int,
    sparse_fraction: float,
    domain: str = DEFAULT_DOMAIN,
) -> list[PatientRecord]:
    if domain not in DOMAIN_LIBS:
        raise ValueError(f"unknown RECORD_DOMAIN {domain!r}; choose from {sorted(DOMAIN_LIBS)}")
    lib = DOMAIN_LIBS[domain]
    rng = random.Random(seed)
    fake = None
    if Faker is not None:
        fake = Faker()
        Faker.seed(seed)
    n_sparse = int(count * sparse_fraction)
    flags = [True] * n_sparse + [False] * (count - n_sparse)
    rng.shuffle(flags)
    return [_mk_record(rng, fake, i + 1, flags[i], lib) for i in range(count)]


def _flatten(rec: PatientRecord) -> dict[str, object]:
    d = rec.model_dump(mode="json")
    return {
        "record_id": d["record_id"],
        "mrn": d["mrn"],
        "given_name": d["given_name"],
        "family_name": d["family_name"],
        "date_of_birth": d["date_of_birth"],
        "sex": d["sex"],
        "care_setting": d["encounter"]["care_setting"],
        "presenting_complaint": d["encounter"]["presenting_complaint"],
        "gestational_age_weeks": d["encounter"]["gestational_age_weeks"],
        "birth_weight_g": d["encounter"]["birth_weight_g"],
        "day_of_life": d["encounter"]["day_of_life"],
        "admitted_at": d["encounter"]["admitted_at"],
        "n_problems": len(d["problems"]),
        "n_medications": len(d["medications"]),
        "n_vitals": len(d["vitals"]),
        "n_labs": len(d["labs"]),
        "dataset_provenance": d["dataset_provenance"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count", type=int, default=200)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--sparse-fraction", type=float, default=0.25)
    p.add_argument("--domain", default=DEFAULT_DOMAIN, choices=sorted(DOMAIN_LIBS))
    p.add_argument("--out", type=Path, default=Path("data/patient_records/synthetic"))
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    records = generate(args.count, args.seed, args.sparse_fraction, args.domain)

    json_path = args.out / "patients.json"
    json_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "dataset_provenance": SYNTHETIC_PROVENANCE,
                "record_domain": args.domain,
                "generated_at": datetime.now(UTC).isoformat(),
                "seed": args.seed,
                "records": [r.model_dump(mode="json") for r in records],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_path = args.out / "patients.csv"
    rows = [_flatten(r) for r in records]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"[gen-data] wrote {len(records)} synthetic '{args.domain}' records:")
    print(f"           {json_path}")
    print(f"           {csv_path}")
    print("           ALL SYNTHETIC. dataset_provenance =", SYNTHETIC_PROVENANCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
