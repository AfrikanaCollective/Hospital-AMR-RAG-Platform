"""Deprecated alias for scripts.prepare_sample_guidelines (DEVIATIONS.md #26).

The dev guideline corpus is operator-provided real PDFs in
`data/excerpt_guidelines/`, not generated content. Use
`python -m scripts.prepare_sample_guidelines` (or `make prepare-guidelines`).
This shim is kept so existing commands / muscle memory still work.
"""

from __future__ import annotations

from scripts.prepare_sample_guidelines import main

if __name__ == "__main__":
    raise SystemExit(main())
