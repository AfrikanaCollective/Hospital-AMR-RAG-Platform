"""Auto-question generation task body (ARCH §15; DEVIATIONS.md #67, #78)."""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.models.eval import EvalQuestion
from app.eval.tasks import _run_generate_questions

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


def test_generates_and_persists_questions(synthetic_records_dir) -> None:  # noqa: ANN001, ARG001
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
