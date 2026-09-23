"""`run_ablation_holdout_generation` — the review-queue-free sibling of
`run_auto_seed_review_queue` (DEVIATIONS.md #199; PRD-112 / ARCH-043)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models.eval import EvalQuestion, Result
from app.eval import auto_seed
from app.eval.question_gen.deterministic import build_deterministic_narrative

RECORD_ID = uuid.uuid4()
RECORD = {
    "record_id": "DEIDREC-000001",
    "mrn": "MRN-1",
    "sex": "male",
    "encounter": {
        "gestational_age_weeks": 34.0,
        "day_of_life": 3,
        "presenting_complaint": "grunting",
    },
    "problems": ["lethargy"],
}
RECORD_TEXT = build_deterministic_narrative(RECORD, topic=auto_seed._TOPIC)


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self) -> None:
        pass

    @property
    def questions(self) -> list[EvalQuestion]:
        return [o for o in self.added if isinstance(o, EvalQuestion)]

    @property
    def results(self) -> list[Result]:
        return [o for o in self.added if isinstance(o, Result)]


def _well_supported_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {
        "observed_outcome": "well_supported",
        "final_answer": {
            "segments": [
                {"type": "claim", "text": "Example Guideline recommends X.", "citation_ids": ["c1"]}
            ],
            "citations": [
                {
                    "citation_id": "c1",
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "document_title": "Example Guideline",
                    "document_version_id": "v1",
                    "version_label": "2024 edition",
                    "quote": "recommends X",
                    "section_number": "1.2",
                    "page_start": 3,
                    "page_end": 3,
                    "char_start": 0,
                    "char_end": 13,
                    "quote_char_start": 0,
                    "quote_char_end": 13,
                }
            ],
        },
    }


def _escalated_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {"observed_outcome": "escalated", "escalation": {"trigger_code": "low_confidence"}}


@pytest.fixture(autouse=True)
def _default_seams(monkeypatch: pytest.MonkeyPatch):
    """Every test overrides the specific seam(s) it cares about; these
    defaults keep the others inert so a test only has to name what it's
    actually exercising."""
    monkeypatch.setattr(auto_seed, "_EXISTING_RECORDS_FN", lambda session: [])  # noqa: ARG005
    yield


def test_writes_only_eval_question_never_a_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert len(created) == 1
    assert len(session.questions) == 1
    assert session.results == []  # the whole point of this pipeline
    assert created[0] == session.questions[0].id


def test_question_always_targets_well_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert session.questions[0].expected_outcome == "well_supported"


def test_gold_relevant_chunks_set_from_the_real_pipelines_own_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert session.questions[0].gold_relevant_chunks == ["chunk-1"]


def test_escalated_pipeline_output_leaves_gold_relevant_chunks_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _escalated_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert len(created) == 1  # still generated -- just no gold chunks
    assert session.questions[0].gold_relevant_chunks is None


def test_generator_meta_marks_the_ablation_holdout_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    auto_seed.run_ablation_holdout_generation(session, target_count=1)
    meta = session.questions[0].generator_meta
    assert meta is not None
    assert meta["purpose"] == "ablation_holdout"


def test_already_at_target_skips_without_loading_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 5)  # noqa: ARG005
    called = {"load": False}

    def _load(*_args: object, **_kwargs: object) -> list:
        called["load"] = True
        return []

    monkeypatch.setattr(auto_seed, "_LOAD_RECORDS_FN", _load)
    created = auto_seed.run_ablation_holdout_generation(_FakeSession(), target_count=5)
    assert created == []
    assert called["load"] is False


def test_tops_up_only_the_remaining_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 2)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=3)
    assert len(created) == 1  # target 3, 2 already exist -> exactly 1 more


def test_excludes_patient_ids_already_used_by_either_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A record already used by `run_auto_seed_review_queue` (or a prior
    ablation-holdout run) must never be drawn again here — both pipelines
    read the SAME `_used_patient_ids` seam (DEVIATIONS.md #114/#199)."""
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: {RECORD_ID})  # noqa: ARG005

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=3)
    assert created == []
    assert session.questions == []


def test_no_deidentified_records_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_LOAD_RECORDS_FN", lambda *a, **k: [])  # noqa: ARG005
    created = auto_seed.run_ablation_holdout_generation(_FakeSession(), target_count=3)
    assert created == []


def test_transient_gateway_error_skips_the_attempt_not_the_whole_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id_2 = uuid.uuid4()
    record_2 = {**RECORD, "record_id": "DEIDREC-000002"}
    calls = {"n": 0}

    def _fails_once_then_succeeds(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            import httpx

            raise httpx.ConnectError("boom")
        return _well_supported_pipeline_output()

    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD), (record_id_2, record_2)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _fails_once_then_succeeds)

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert len(created) == 1
    assert calls["n"] == 2  # one failed attempt, one that succeeded


def test_rejects_a_narrative_matching_an_already_accepted_records_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_id_2 = uuid.uuid4()
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_ABLATION_HOLDOUT_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(record_id_2, dict(RECORD, record_id="DUP"))],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_EXISTING_RECORDS_FN", lambda session: [RECORD])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_ablation_holdout_generation(session, target_count=1)
    assert created == []
    assert session.questions == []
