"""Auto-question generation task body (ARCH §15; DEVIATIONS.md #67, #78, #151)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

import app.eval.tasks as tasks_mod
from app.db.models.eval import EvalQuestion
from app.eval.tasks import _run_generate_deterministic_questions, _run_generate_questions
from app.llm.gateway import LLMGatewayError
from app.schemas.enums import ExpectedOutcome

RECORD = {
    "record_id": "SYNREC-000001",
    "mrn": "MRN-1",
    "sex": "male",
    "encounter": {
        "gestational_age_weeks": 34.0,
        "day_of_life": 3,
        "presenting_complaint": "grunting",
    },
    "problems": ["lethargy"],
}

GOOD_QUESTION = (
    "What does the guideline recommend for a male newborn at 34 weeks "
    "gestation presenting with grunting and lethargy?"
)


class _FakeChatResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model_id = "fake-model"
        self.usage: dict = {}


class _FakeGateway:
    def chat(self, *, system: str, messages: list[dict], **params: object) -> _FakeChatResult:  # noqa: ARG002
        return _FakeChatResult(GOOD_QUESTION)


def _well_supported_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {
        "observed_outcome": "well_supported",
        "final_answer": {
            "citations": [
                {"chunk_id": "chunk-2"},
                {"chunk_id": "chunk-1"},
                {"chunk_id": "chunk-1"},  # duplicate -- gold set must dedupe
            ]
        },
    }


def _escalated_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {"escalation": {"trigger_code": "grounding_failure"}}


def _no_citations_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {"observed_outcome": "well_supported", "final_answer": {"citations": []}}


def _flaky_pipeline(*_args: object, **_kwargs: object) -> dict:
    raise httpx.HTTPError("boom")


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[EvalQuestion] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()


@pytest.fixture
def synthetic_records_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001
    records_dir = tmp_path / "patient_records"
    (records_dir / "synthetic").mkdir(parents=True)
    payload = {
        "schema_version": "1.2.0",
        "dataset_provenance": "synthetic-generator-v1",
        "records": [RECORD],
    }
    (records_dir / "synthetic" / "patients.json").write_text(json.dumps(payload))
    monkeypatch.setenv("PATIENT_RECORDS_DIR", str(records_dir))
    from app.config import get_settings

    get_settings.cache_clear()
    yield records_dir
    get_settings.cache_clear()


def test_generates_and_persists_questions(
    synthetic_records_dir,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001, ARG001
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)
    session = _FakeSession()
    ids = _run_generate_questions(
        session, count=5, composition="60,20,20", seed=1, gateway=_FakeGateway()
    )
    assert len(ids) == len(session.added)
    assert len(session.added) > 0
    assert all(q.in_fixed_testset for q in session.added)
    assert {q.expected_outcome for q in session.added} <= {
        "well_supported",
        "missing_info_expected",
        "no_guideline_expected",
    }


def test_no_records_raises(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("PATIENT_RECORDS_DIR", str(tmp_path / "empty"))
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        _run_generate_questions(
            _FakeSession(), count=3, composition="100,0,0", gateway=_FakeGateway()
        )
    get_settings.cache_clear()


def test_generated_question_gets_gold_relevant_chunks_from_real_citations(
    synthetic_records_dir,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001, ARG001
) -> None:
    """DEVIATIONS.md #151: fixes the gap #122 identified — this generator now
    invokes the real pipeline once per question and takes its own
    grounding-verified citations as the gold set, deduped and sorted."""
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)
    session = _FakeSession()
    _run_generate_questions(session, count=1, composition="100,0,0", seed=1, gateway=_FakeGateway())
    assert len(session.added) == 1
    assert session.added[0].gold_relevant_chunks == ["chunk-1", "chunk-2"]


def test_escalated_pipeline_leaves_gold_relevant_chunks_unset(
    synthetic_records_dir,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001, ARG001
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _escalated_pipeline_output)
    session = _FakeSession()
    _run_generate_questions(session, count=1, composition="100,0,0", seed=1, gateway=_FakeGateway())
    assert session.added[0].gold_relevant_chunks is None


def test_no_citations_leaves_gold_relevant_chunks_unset(
    synthetic_records_dir,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001, ARG001
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _no_citations_pipeline_output)
    session = _FakeSession()
    _run_generate_questions(session, count=1, composition="100,0,0", seed=1, gateway=_FakeGateway())
    assert session.added[0].gold_relevant_chunks is None


def test_transient_gateway_error_capturing_gold_chunks_does_not_fail_the_batch(
    synthetic_records_dir,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001, ARG001
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _flaky_pipeline)
    session = _FakeSession()
    ids = _run_generate_questions(
        session, count=1, composition="100,0,0", seed=1, gateway=_FakeGateway()
    )
    assert len(ids) == 1  # the question itself is still created
    assert session.added[0].gold_relevant_chunks is None


def test_capture_gold_relevant_chunks_swallows_llm_gateway_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_a: object, **_kw: object) -> dict:
        raise LLMGatewayError("gateway down")

    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _raise)
    assert tasks_mod._capture_gold_relevant_chunks("some question") is None


# ── _run_generate_deterministic_questions (DEVIATIONS.md #156) ──────────────


def test_deterministic_generation_creates_one_question_per_synthetic_record(
    synthetic_records_dir,  # noqa: ANN001, ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)
    session = _FakeSession()
    ids = _run_generate_deterministic_questions(session, topic="antibiotics or infection")
    assert len(ids) == 1  # one bundled synthetic record in the fixture
    q = session.added[0]
    assert q.text.startswith("What does the guideline recommend about antibiotics or infection")
    assert q.provenance == "auto_generated"
    assert q.expected_outcome == ExpectedOutcome.WELL_SUPPORTED
    assert q.target_guideline_ref == {"topic": "antibiotics or infection"}
    assert q.generator_meta == {"template_version": "deterministic-v1"}
    assert q.in_fixed_testset is False  # default, unlike the LLM generator


def test_deterministic_generation_also_captures_gold_relevant_chunks(
    synthetic_records_dir,  # noqa: ANN001, ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)
    session = _FakeSession()
    _run_generate_deterministic_questions(session, topic="x")
    assert session.added[0].gold_relevant_chunks == ["chunk-1", "chunk-2"]


def test_deterministic_generation_source_record_id_matches_llm_path_hash(
    synthetic_records_dir,  # noqa: ANN001, ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same uuid5(record_id) scheme as `_run_generate_questions`, so both
    paths' questions resolve via the same
    `app.eval.orchestration_ablation.augment.resolve_source_record`."""
    monkeypatch.setattr(tasks_mod, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)
    session = _FakeSession()
    _run_generate_deterministic_questions(session, topic="x")
    expected = uuid.uuid5(tasks_mod._RECORD_ID_NAMESPACE, RECORD["record_id"])
    assert session.added[0].source_record_id == expected


def test_deterministic_generation_no_records_raises(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    monkeypatch.setenv("PATIENT_RECORDS_DIR", str(tmp_path / "empty"))
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        _run_generate_deterministic_questions(_FakeSession(), topic="x")
    get_settings.cache_clear()
