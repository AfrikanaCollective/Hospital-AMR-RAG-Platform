"""Prepare the development guideline corpus (PRD-006, PRD-001, PRD-A2; ARCH-038).

Default behaviour — **use the real guideline documents the operator has placed
in `SAMPLE_GUIDELINES_DIR`** (default `data/sample_guidelines/`). This script
does NOT generate guideline content by default. It:

  1. scans the directory for guideline files (`*.pdf`, `*.md`), ignoring the
     `SYNTH-GL-*` fixtures, `SOURCES.md`, and `manifest*.json`;
  2. loads `manifest.json` (copy `manifest.example.json` to start) and checks
     each document has a complete metadata entry — it **warns, it never
     invents** missing metadata (ARCH-038);
  3. prints a summary table and exits 0 (or non-zero with `--strict`).

Fallback — only when there are NO real documents AND `--allow-synthetic` (or
`GUIDELINES_ALLOW_SYNTHETIC=true`): write a tiny synthetic 3-document set into
`backend/tests/fixtures/guidelines/` as a **CI-only offline fixture** (never
into the real corpus dir). See DEVIATIONS.md #26.

Usage:
    python -m scripts.prepare_sample_guidelines [--dir DIR] [--strict] [--allow-synthetic]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_MANIFEST_FIELDS = ("title", "publisher", "version_label", "effective_date", "licence")
PLACEHOLDER_TOKENS = ("TODO_CONFIRM", "TODO", "<set-me>", "")

# CI-only synthetic fixtures — NOT clinical guidance, NOT the real corpus.
_SYNTHETIC_FIXTURES: dict[str, str] = {
    "SYNTH-GL-001_acute_breathlessness.md": """# SYNTHETIC GUIDELINE 001 — Assessment of Acute Breathlessness in Adults
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2025.1 — effective 2025-01-01
format_profile: grade_recommendations

## 1. Scope
1.1 Initial assessment of adults presenting with acute breathlessness in hospital.

## 2. Initial assessment
### 2.1 Immediate observations
2.1.1 The guideline recommends recording respiratory rate, oxygen saturation,
heart rate, and blood pressure at presentation. (Strong recommendation, low certainty)

### 2.2 Oxygen
2.2.1 Per this guideline, supplemental oxygen is recommended to maintain
saturations within a documented target range. (Strong recommendation, moderate certainty)

## 3. Stage-of-care criteria
| Stage | Criteria (all required) |
|---|---|
| Initial assessment | Within 1 hour of arrival; observations not yet complete |
| Stabilisation | Observations complete; oxygen target set; senior review requested |
| Ongoing management | Stabilised for >= 4 hours; disposition decision documented |
""",
    "SYNTH-GL-002_hospital_acquired_infection.md": """# SYNTHETIC GUIDELINE 002 — Suspected Hospital-Acquired Infection
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2024.2 — effective 2024-06-01
format_profile: grade_recommendations

## 2. Investigations
2.1.1 This guideline recommends blood cultures before antimicrobials where this
does not delay treatment beyond one hour. (Strong recommendation, moderate certainty)

## 3. Antimicrobial choice
3.1.1 Empirical antimicrobial choice should follow the local formulary. Where
the first-line agent is contraindicated, the guideline lists a documented
second-line agent for each syndrome in Appendix A.

## 4. Required information
4.1 Before a syndrome-specific recommendation can be applied, the guideline
requires: suspected source, time of onset relative to admission, and current
renal function.
""",
    "SYNTH-GL-003_narrow_topic_electrolytes.md": """# SYNTHETIC GUIDELINE 003 — Replacement of Low Potassium in Adult Inpatients
*THIS IS A SYNTHETIC DOCUMENT FOR SOFTWARE DEVELOPMENT. NOT CLINICAL GUIDANCE.*
Version 2025.1 — effective 2025-03-01
format_profile: grade_recommendations

## 2. Thresholds
2.1.1 Replacement is considered when the serum potassium is below a stated
threshold and renal function is known. (Strong recommendation, moderate certainty)

## 3. Required information
3.1 The guideline requires a serum potassium result within the last 24 hours
and a current creatinine before replacement is planned.
""",
}

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "guidelines"


def _is_guideline_file(p: Path) -> bool:
    if p.suffix.lower() not in (".pdf", ".md"):
        return False
    if p.name.startswith("SYNTH-GL-"):
        return False
    if p.name in ("SOURCES.md",):
        return False
    return True


def _page_count(pdf: Path) -> int | str:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return "?"


def _load_manifest(dir_: Path) -> dict:
    mf = dir_ / "manifest.json"
    if mf.exists():
        return json.loads(mf.read_text(encoding="utf-8")).get("files", {})
    return {}


def _entry_incomplete(entry: dict | None) -> list[str]:
    if not entry:
        return list(REQUIRED_MANIFEST_FIELDS)
    missing = []
    for f in REQUIRED_MANIFEST_FIELDS:
        v = str(entry.get(f, "")).strip()
        if v in PLACEHOLDER_TOKENS or v.startswith("TODO_CONFIRM"):
            missing.append(f)
    return missing


def use_real_corpus(dir_: Path, strict: bool) -> int:
    docs = sorted(p for p in dir_.iterdir() if _is_guideline_file(p))
    manifest = _load_manifest(dir_)
    print(f"[prepare-guidelines] {len(docs)} guideline document(s) in {dir_}")
    if not (dir_ / "manifest.json").exists():
        print(f"[prepare-guidelines] NOTE: no manifest.json — copy "
              f"{dir_ / 'manifest.example.json'} to manifest.json and fill it (ARCH-038).")
    any_incomplete = False
    print(f"\n  {'file':<62} {'pages':>6}  {'profile':<20} {'metadata'}")
    print(f"  {'-' * 62} {'-' * 6}  {'-' * 20} {'-' * 8}")
    for p in docs:
        entry = manifest.get(p.name)
        missing = _entry_incomplete(entry)
        pages = _page_count(p) if p.suffix.lower() == ".pdf" else "-"
        profile = (entry or {}).get("format_profile", "(detect)")
        status = "OK" if not missing else f"MISSING: {', '.join(missing)}"
        if missing:
            any_incomplete = True
        name = p.name if len(p.name) <= 62 else p.name[:59] + "..."
        print(f"  {name:<62} {str(pages):>6}  {profile:<20} {status}")

    if any_incomplete:
        print("\n[prepare-guidelines] WARNING: one or more documents have incomplete "
              "manifest metadata. Fill the fields above in manifest.json — this "
              "script will not invent them (ARCH-038).")
        return 1 if strict else 0
    print("\n[prepare-guidelines] all documents have complete metadata.")
    return 0


def write_synthetic_fixtures() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, body in _SYNTHETIC_FIXTURES.items():
        (FIXTURES_DIR / name).write_text(body, encoding="utf-8")
    (FIXTURES_DIR / "README.md").write_text(
        "# Synthetic guideline fixtures (CI-only)\n\n"
        f"Generated {datetime.now(UTC).isoformat()} by "
        "`scripts/prepare_sample_guidelines.py --allow-synthetic`.\n\n"
        "These are **NOT real clinical guidance** and are **NOT** the dev corpus. "
        "The real corpus is operator-provided PDFs in `data/sample_guidelines/` "
        "(see DEVIATIONS.md #26). Use these only for deterministic offline tests.\n",
        encoding="utf-8",
    )
    print(f"[prepare-guidelines] wrote {len(_SYNTHETIC_FIXTURES)} CI-only synthetic "
          f"fixtures to {FIXTURES_DIR}")
    print("[prepare-guidelines] these are NOT the dev corpus — add real guideline "
          "PDFs to data/sample_guidelines/ for real work.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path,
                   default=Path(os.environ.get("SAMPLE_GUIDELINES_DIR", "data/sample_guidelines")))
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if any document's manifest metadata is incomplete")
    p.add_argument("--allow-synthetic", action="store_true",
                   help="when no real docs are present, write the CI-only synthetic fixture set")
    args = p.parse_args(argv)

    allow_synth = args.allow_synthetic or os.environ.get("GUIDELINES_ALLOW_SYNTHETIC", "").lower() in (
        "1", "true", "yes",
    )

    args.dir.mkdir(parents=True, exist_ok=True)
    real_docs = [x for x in args.dir.iterdir() if _is_guideline_file(x)]

    if real_docs:
        return use_real_corpus(args.dir, strict=args.strict)
    if allow_synth:
        return write_synthetic_fixtures()

    print(f"[prepare-guidelines] No guideline documents found in {args.dir}.\n"
          "  Add real guideline PDFs there and give each a manifest.json entry "
          "(copy manifest.example.json), then re-run.\n"
          "  Or pass --allow-synthetic (GUIDELINES_ALLOW_SYNTHETIC=true) to write "
          "the CI-only offline fixture set instead.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
