"""Synthetic patient-record generator (PRD-006, PRD-081; ARCH §5.2).

Produces SYNTHETIC-ONLY patient records as both JSON (one array) and CSV (one
flat row per record). Deterministic given --seed. Output is marked with
`dataset_provenance = "synthetic-generator-v1"` so the ingestion real-data
heuristic accepts it (DEVIATIONS.md #21).

A configurable fraction of records is deliberately SPARSE (required-ish fields
nulled) to support hard-case ("missing_info_expected") question generation
later (PRD-064).

Usage:
    python -m scripts.generate_synthetic_records --count 200 --out ../data/synthetic_records
"""

from __future__ import annotations

import argparse
import csv
import json
import random
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

CARE_SETTINGS = ["ED", "general ward", "HDU", "ICU", "surgical ward", "medical ward"]
COMPLAINTS = [
    "shortness of breath", "chest pain", "fever and cough", "abdominal pain",
    "confusion", "fall", "vomiting", "reduced urine output", "leg swelling",
    "headache", "back pain", "palpitations",
]
PROBLEMS = [
    "type 2 diabetes mellitus", "hypertension", "chronic kidney disease stage 3",
    "atrial fibrillation", "COPD", "heart failure", "asthma", "ischaemic heart disease",
]
DRUGS = [
    ("amoxicillin", "500 mg", "oral", "TDS"),
    ("furosemide", "40 mg", "IV", "OD"),
    ("metformin", "1 g", "oral", "BD"),
    ("apixaban", "5 mg", "oral", "BD"),
    ("paracetamol", "1 g", "oral", "QDS"),
    ("salbutamol", "5 mg", "neb", "PRN"),
]
LAB_ANALYTES = [
    ("creatinine", "umol/L", 50, 350, 60, 110),
    ("potassium", "mmol/L", 2.8, 6.5, 3.5, 5.3),
    ("haemoglobin", "g/L", 70, 175, 120, 165),
    ("white cell count", "10^9/L", 2.0, 25.0, 4.0, 11.0),
    ("C-reactive protein", "mg/L", 1, 350, 0, 5),
    ("lactate", "mmol/L", 0.4, 8.0, 0.5, 2.0),
]


def _mk_record(rng: random.Random, fake: object, idx: int, sparse: bool) -> PatientRecord:
    admitted = datetime.now(UTC) - timedelta(hours=rng.randint(2, 240))
    given = fake.first_name() if fake else f"Synth{idx:04d}"
    family = fake.last_name() if fake else f"Patient{idx:04d}"

    n_vitals = 0 if sparse and rng.random() < 0.5 else rng.randint(1, 4)
    vitals = [
        Vitals(
            recorded_at=admitted + timedelta(hours=h * 6),
            heart_rate_bpm=rng.randint(50, 130),
            resp_rate_bpm=rng.randint(10, 34),
            systolic_bp_mmhg=rng.randint(80, 180),
            diastolic_bp_mmhg=rng.randint(45, 105),
            temperature_c=round(rng.uniform(35.5, 39.8), 1),
            spo2_percent=rng.randint(85, 100),
        )
        for h in range(n_vitals)
    ]

    n_labs = 0 if sparse and rng.random() < 0.6 else rng.randint(1, 5)
    labs: list[LabResult] = []
    for analyte, unit, lo, hi, rlo, rhi in rng.sample(LAB_ANALYTES, k=min(n_labs, len(LAB_ANALYTES))):
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
        for (n, d, r, f) in rng.sample(DRUGS, k=0 if sparse else rng.randint(0, 4))
    ]

    return PatientRecord(
        schema_version=SCHEMA_VERSION,
        dataset_provenance=SYNTHETIC_PROVENANCE,
        record_id=f"SYNREC-{idx:06d}",
        mrn=f"SYN-{idx:08d}",
        given_name=given,
        family_name=family,
        date_of_birth=None if sparse and rng.random() < 0.3
        else (datetime.now(UTC).date() - timedelta(days=rng.randint(365 * 18, 365 * 95))),
        sex=rng.choice(["female", "male", "unknown"]),
        encounter=Encounter(
            admitted_at=admitted,
            ward=None if sparse else rng.choice(["4A", "4B", "6C", "ICU", "AMU"]),
            care_setting=None if sparse and rng.random() < 0.4 else rng.choice(CARE_SETTINGS),
            presenting_complaint=None if sparse and rng.random() < 0.2
            else rng.choice(COMPLAINTS),
            triage_category=None if sparse else str(rng.randint(1, 5)),
        ),
        problems=[] if sparse else rng.sample(PROBLEMS, k=rng.randint(0, 3)),
        allergies=[] if rng.random() < 0.7 else ["penicillin"],
        medications=meds,
        vitals=vitals,
        labs=labs,
        clinical_notes=None if sparse
        else f"Synthetic note: admitted with {rng.choice(COMPLAINTS)}; for review.",
        consent_flags={"research_opt_out": rng.random() < 0.1},
    )


def generate(count: int, seed: int, sparse_fraction: float) -> list[PatientRecord]:
    rng = random.Random(seed)
    fake = None
    if Faker is not None:
        fake = Faker()
        Faker.seed(seed)
    n_sparse = int(count * sparse_fraction)
    flags = [True] * n_sparse + [False] * (count - n_sparse)
    rng.shuffle(flags)
    return [_mk_record(rng, fake, i + 1, flags[i]) for i in range(count)]


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
    p.add_argument("--out", type=Path, default=Path("data/synthetic_records"))
    args = p.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    records = generate(args.count, args.seed, args.sparse_fraction)

    json_path = args.out / "patients.json"
    json_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "dataset_provenance": SYNTHETIC_PROVENANCE,
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

    print(f"[gen-data] wrote {len(records)} synthetic records:")
    print(f"           {json_path}")
    print(f"           {csv_path}")
    print("           ALL SYNTHETIC. dataset_provenance =", SYNTHETIC_PROVENANCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
