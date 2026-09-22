"""Per-query result persistence (UNIFIED-ABLATION-PROPOSAL.md §3.5, §4
point 2; PRD-112, requirement IX).

File-based, not a Postgres table (operator decision, proposal §4 point 2):

    results/
    └── ablation/
        └── <run_id>/
            ├── configuration.json       # reproducibility snapshot, §3.8
            └── per_query_results.jsonl  # one line per (query, arm, k, alpha)
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

_DEFAULT_RESULTS_ROOT = Path("results/ablation")


@dataclass(frozen=True)
class PerQueryResult:
    """One row per (query, level1, level2, level3, alpha, k) — exactly the
    fields requirement IX lists. The same query is evaluated under all 16
    Level-1 x Level-2 x Level-3 leaf conditions (each swept over its own
    alpha/k grid, `app.eval.ablation_config`), so `query_id` repeats across
    many rows by design — that's what makes the paired comparisons in §3.7
    possible."""

    query_id: str
    patient_id_or_case_id: str
    experiment_id: str

    level1_condition: str
    level2_condition: str
    level3_condition: str

    k: int
    alpha: float

    query_text: str
    concept_enriched_query: str

    retrieved_ids: list[str]
    relevant_ids: list[str]

    first_relevant_rank: int | None
    reciprocal_rank_at_k: float

    def to_json_dict(self) -> dict:
        return asdict(self)


def run_dir_for(run_id: str, *, results_root: Path | None = None) -> Path:
    root = results_root if results_root is not None else _DEFAULT_RESULTS_ROOT
    d = root / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_configuration(run_dir: Path, config: dict) -> Path:
    path = run_dir / "configuration.json"
    path.write_text(json.dumps(config, indent=2, default=str), encoding="utf-8")
    return path


def write_per_query_results(run_dir: Path, rows: Iterable[PerQueryResult]) -> Path:
    """Streams rows to disk one line at a time rather than building the
    whole list in memory first — a real run's row count is large (16 arms x
    up to 6 alphas x `len(K_VALUES)` k's per query, x up to 100 queries)."""
    path = run_dir / "per_query_results.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.to_json_dict()) + "\n")
    return path


def read_per_query_results(path: Path) -> list[PerQueryResult]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            rows.append(PerQueryResult(**json.loads(stripped)))
    return rows
