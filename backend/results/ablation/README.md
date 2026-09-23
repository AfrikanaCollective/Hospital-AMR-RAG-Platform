# `results/ablation/` — unified hierarchical ablation run output

Written by `python -m scripts.run_unified_ablation` (PRD-112 / ARCH-043,
`UNIFIED-ABLATION-PROPOSAL.md` §4 point 2). One subdirectory per run:

```
results/ablation/<run_id>/
├── configuration.json       # reproducibility snapshot (model ids/versions,
│                             K/alpha grids, seed, timestamp, template
│                             version, vocabulary-attestation status)
├── per_query_results.jsonl  # one JSON line per (query, level1, level2,
│                             level3, alpha, k) row — see
│                             app.eval.unified_ablation.per_query.PerQueryResult
│                             for the exact field list
└── unified_ablation_report.png  # combined 3-panel summary (Level 1/2/3)
```

**Never committed** — `per_query_results.jsonl` can run into the hundreds
of MB per run (a single 238-question run against this deployment's real
16-arm × 10-k × 6-alpha grid produced 180,880 rows / 472MB — DEVIATIONS.md
#197). `.gitignore` excludes everything under this directory except this
file and `.gitkeep`.
