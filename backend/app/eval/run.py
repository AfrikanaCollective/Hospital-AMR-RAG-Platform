"""CLI: python -m app.eval.run --snapshot <id>  (ARCH §16; Makefile `make eval`).

Phase 3 wires this to app.eval.harness.run_harness and prints/persists the
report, exiting non-zero on a gating breach.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation harness (ARCH §16).")
    parser.add_argument("--snapshot", default="latest")
    parser.add_argument("--no-fail", action="store_true", help="do not exit non-zero on breach")
    args = parser.parse_args(argv)
    print(f"[eval] snapshot={args.snapshot}: harness not implemented until Phase 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
