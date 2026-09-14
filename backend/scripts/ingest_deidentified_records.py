"""Ingest an operator-supplied, attested de-identified patient dataset
(ARCH-039; DEVIATIONS #33, #34).

Reads an EAV/long CSV + a `field_mapping.yaml`, pivots long->wide, maps each
patient onto `app/schemas/record.py`, validates, and writes a normalized JSON
batch. Refuses to run without `--attest-deidentified` AND a `DATASET.md` whose
YAML front-matter carries a complete operator attestation.

`--persist` additionally writes to the database (`app.ingestion.records.ingest_records`
— Patient dedup on MRN via `patient.mrn_hash`, DEVIATIONS.md #57;
envelope-encrypted `payload_enc`, `field_index`; ARCH §5.2) via
`app.db.session.session_scope`. Without it, the script only writes the
normalized JSON file, as before.

Usage:
    python -m scripts.ingest_deidentified_records \
      --dataset-dir ../data/patient_records/deidentified/newborn_nbu_2021 \
      --attest-deidentified --persist --limit 500
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.ingestion.records import DatasetAttestation, guard_batch
from app.ingestion.sources import FileEavSource


def parse_front_matter(md_path: Path) -> dict[str, str]:
    """Return the YAML front-matter dict from a `--- ... ---` fenced block."""
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    fm, _, _ = rest.partition("\n---")
    data = yaml.safe_load(fm) or {}
    return {k: ("" if v is None else str(v)) for k, v in data.items()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="dir containing rag_dataset.csv, field_mapping.yaml, DATASET.md",
    )
    p.add_argument("--csv", type=Path, default=None)
    p.add_argument("--mapping", type=Path, default=None)
    p.add_argument("--dataset-md", type=Path, default=None)
    p.add_argument(
        "--attest-deidentified",
        action="store_true",
        help="required: operator attests the dataset is de-identified per DATASET.md",
    )
    p.add_argument(
        "--persist",
        action="store_true",
        help="also write to the database (app.ingestion.records.ingest_records)",
    )
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    d = args.dataset_dir
    csv_path = args.csv or (d / "rag_dataset.csv")
    mapping_path = args.mapping or (d / "field_mapping.yaml")
    dataset_md = args.dataset_md or (d / "DATASET.md")
    out_path = args.out or (d / "records.normalized.json")

    if not args.attest_deidentified:
        print(
            "[ingest-deid] refused: pass --attest-deidentified to confirm this dataset "
            "is de-identified per its DATASET.md (DEVIATIONS #33).",
            file=sys.stderr,
        )
        return 2

    for pth in (csv_path, mapping_path, dataset_md):
        if not pth.exists():
            print(f"[ingest-deid] missing required file: {pth}", file=sys.stderr)
            return 2

    attestation = DatasetAttestation(values=parse_front_matter(dataset_md))
    missing = attestation.missing_fields()
    if missing:
        print(
            f"[ingest-deid] refused: DATASET.md attestation incomplete — fill: {missing}",
            file=sys.stderr,
        )
        return 2

    src = FileEavSource(csv_path, mapping_path)
    desc = src.describe()
    records = list(src.iter_records(limit=args.limit))
    data_class = guard_batch(records, declared_provenance=desc.provenance, attestation=attestation)

    out_path.write_text(
        json.dumps(
            {
                "schema_version": records[0].schema_version if records else None,
                "dataset_id": desc.dataset_id,
                "data_class": str(data_class),
                "dataset_provenance": desc.provenance,
                "ingested_at": datetime.now(UTC).isoformat(),
                "attestation": attestation.values,
                "count": len(records),
                "records": [r.model_dump(mode="json") for r in records],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"[ingest-deid] {desc.dataset_id}: mapped {len(records)} de-identified records "
        f"({data_class}) -> {out_path}"
    )
    print("[ingest-deid] handled as PHI end to end (encryption / RBAC / audit / no egress).")

    if args.persist:
        # Lazy: only needed for --persist, same convention as parse_front_matter's `yaml` import.
        from app.db.session import session_scope  # noqa: PLC0415
        from app.ingestion.records import ingest_records  # noqa: PLC0415

        with session_scope() as session:
            ids = ingest_records(
                session,
                records,
                declared_provenance=desc.provenance,
                dataset_id=desc.dataset_id,
                attestation=attestation,
                source="eav_file",
            )
        print(f"[ingest-deid] persisted {len(ids)} patient_record row(s) to the database.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
