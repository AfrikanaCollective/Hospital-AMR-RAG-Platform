"""CLI: python -m app.eval.run --snapshot <id>  (ARCH §16; Makefile `make eval`).

Wired to app.eval.harness.run_harness; prints the report and exits non-zero
on a gating breach (`EvalGateFailure`) unless `--no-fail` is given.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.eval.harness import EvalGateFailure, run_harness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the evaluation harness (ARCH §16).")
    parser.add_argument("--snapshot", default="latest")
    parser.add_argument("--no-fail", action="store_true", help="do not exit non-zero on breach")
    args = parser.parse_args(argv)

    try:
        report = run_harness(snapshot=args.snapshot, fail_on_threshold_breach=not args.no_fail)
    except EvalGateFailure as exc:
        print(f"[eval] GATING BREACH: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report.model_dump(mode="json"), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
