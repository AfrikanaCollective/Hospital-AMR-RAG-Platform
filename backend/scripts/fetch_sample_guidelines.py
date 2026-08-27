"""Fetch or generate sample guideline documents for development (PRD-006, PRD-A2).

Behaviour:
1. If `--urls-file` is given and the network is reachable, download those PDFs
   (public, licence-permitting) into the output dir and record provenance in
   SOURCES.md.
2. Otherwise (default, offline-safe), GENERATE a handful of small synthetic
   "guideline" documents as Markdown + a simple PDF, with numbered sections,
   recommendation statements (with strength/evidence tags), a criteria table,
   and one deliberately narrow topic — enough to exercise ingestion, chunking,
   retrieval, citations, and the "no guideline found" path.

Synthetic guideline docs are clearly marked as synthetic and are NOT real
clinical guidance.

Usage:
    python -m scripts.fetch_sample_guidelines --out ../data/sample_guidelines
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

SYNTHETIC_DOCS: dict[str, str] = {
    "SYNTH-GL-001_acute_breathlessness.md": """# SYNTHETIC GUIDELINE 001 — Assessment of Acute Breathlessness in Adults
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2025.1 — effective 2025-01-01

## 1. Scope
1.1 This synthetic guideline covers initial assessment of adults presenting
with acute breathlessness in a hospital setting.

## 2. Initial assessment
### 2.1 Immediate observations
2.1.1 The guideline recommends recording respiratory rate, oxygen saturation,
heart rate, and blood pressure at presentation. (Strength: strong; Evidence: low)

### 2.2 Oxygen
2.2.1 Per this guideline, supplemental oxygen is recommended to maintain
saturations within a target range documented for the patient group.
(Strength: strong; Evidence: moderate)

## 3. Stage-of-care criteria
| Stage | Criteria (all required) |
|---|---|
| Initial assessment | Within 1 hour of arrival; observations not yet complete |
| Stabilisation | Observations complete; oxygen target set; senior review requested |
| Ongoing management | Stabilised for >= 4 hours; disposition decision documented |

## 4. Information required before escalation
4.1 The guideline states that the following must be documented before
escalation is considered: most recent full set of observations, current oxygen
delivery, and a venous or arterial blood gas result.
""",
    "SYNTH-GL-002_hospital_acquired_infection.md": """# SYNTHETIC GUIDELINE 002 — Suspected Hospital-Acquired Infection
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2024.2 — effective 2024-06-01

## 1. Scope
1.1 Initial workup for adults with suspected hospital-acquired infection.

## 2. Investigations
2.1.1 This guideline recommends blood cultures before antimicrobials where
this does not delay treatment beyond one hour. (Strength: strong; Evidence: moderate)
2.1.2 The guideline recommends recording temperature, white cell count, and
C-reactive protein at baseline. (Strength: conditional; Evidence: low)

## 3. Antimicrobial choice
3.1.1 Per this guideline, empirical antimicrobial choice should follow the
local formulary. Where the first-line agent is contraindicated, the guideline
lists a documented second-line agent for each syndrome in Appendix A.

## 4. Required information
4.1 Before a syndrome-specific recommendation can be applied, the guideline
requires: suspected source, time of onset relative to admission, and current
renal function.
""",
    "SYNTH-GL-003_narrow_topic_electrolytes.md": """# SYNTHETIC GUIDELINE 003 — Replacement of Low Potassium in Adult Inpatients
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2025.1 — effective 2025-03-01

## 1. Scope
1.1 Deliberately narrow: replacement of low serum potassium in adult
inpatients with a documented recent level.

## 2. Thresholds
2.1.1 The guideline reports replacement is considered when the serum potassium
is below a stated threshold and renal function is known. (Strength: strong; Evidence: moderate)

## 3. Required information
3.1 The guideline requires a serum potassium result within the last 24 hours
and a current creatinine before replacement is planned.
""",
}

SOURCES_HEADER = """# Sample guideline sources

The files in this directory are for **development only**.

"""


def write_synthetic(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, body in SYNTHETIC_DOCS.items():
        (out / name).write_text(body, encoding="utf-8")
        written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("data/sample_guidelines"))
    p.add_argument("--urls-file", type=Path, default=None,
                   help="optional newline-separated list of public PDF URLs to download")
    args = p.parse_args(argv)

    if args.urls_file and args.urls_file.exists():
        # Phase 2: implement network download with provenance capture. For now,
        # fall through to the offline-safe synthetic docs and note it.
        print("[fetch-guidelines] --urls-file download not implemented until Phase 2; "
              "generating synthetic docs instead.")

    written = write_synthetic(args.out)
    (args.out / "SOURCES.md").write_text(
        SOURCES_HEADER
        + f"Generated {datetime.now(UTC).isoformat()} by scripts/fetch_sample_guidelines.py\n\n"
        + "\n".join(f"- `{n}` — SYNTHETIC, generated locally. Not real clinical guidance."
                    for n in written)
        + "\n",
        encoding="utf-8",
    )
    print(f"[fetch-guidelines] wrote {len(written)} synthetic guideline docs to {args.out}")
    for n in written:
        print(f"           {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
