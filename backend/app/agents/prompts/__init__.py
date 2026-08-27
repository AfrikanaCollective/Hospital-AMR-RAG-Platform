"""Versioned agent prompt templates (ARCH §9.1, ARCH-037; SCOPE-1.2).

Templates are .md files loaded by name + version. The reported-content framing
rules ("Guideline X recommends…", never "You should…") are a REQUIREMENT of
every guideline-touching template, not a UI nicety. The deterministic wording
filter (app.grounding.wording) is the second line of defense.
"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def load(name: str, version: str = "v1") -> str:
    path = _DIR / f"{name}.{version}.md"
    if not path.exists():  # v1 files are named without the version suffix in Phase 1
        path = _DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")
