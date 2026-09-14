"""`python -m app.eval.run` CLI (ARCH §16; Makefile `make eval`)."""

from __future__ import annotations

import app.eval.run as run_cli
from app.schemas.eval import EvalRunReport


def _report(passed: bool) -> EvalRunReport:
    return EvalRunReport(run_id="r1", config_snapshot={}, corpus_snapshot_id="", passed=passed)


def test_passing_run_exits_zero(monkeypatch, capsys) -> None:  # noqa: ANN001
    monkeypatch.setattr(run_cli, "run_harness", lambda **kw: _report(True))  # noqa: ARG005
    code = run_cli.main(["--snapshot", "latest"])
    assert code == 0
    assert '"passed": true' in capsys.readouterr().out


def test_gate_failure_exits_nonzero(monkeypatch, capsys) -> None:  # noqa: ANN001
    def _raise(**kwargs):  # noqa: ANN003, ARG001
        raise run_cli.EvalGateFailure("boom")

    monkeypatch.setattr(run_cli, "run_harness", _raise)
    code = run_cli.main([])
    assert code == 1
    assert "GATING BREACH" in capsys.readouterr().err


def test_no_fail_flag_forwarded(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    def _fake(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return _report(False)

    monkeypatch.setattr(run_cli, "run_harness", _fake)
    code = run_cli.main(["--no-fail"])
    assert captured["fail_on_threshold_breach"] is False
    assert code == 1  # report itself still reports not-passed
