"""Auto-seed the review queue from de-identified records (ARCH §14.2, §15;
DEVIATIONS.md #113)."""

from __future__ import annotations

import uuid

import pytest

from app.db.models.eval import EvalQuestion, Result
from app.eval import auto_seed

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
        self.added: list = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    def commit(self) -> None:
        # DEVIATIONS.md #115: `_generate_one_scenario` commits per scenario
        # now. This fake has no real transaction to commit — `.add`/`.flush`
        # already make everything visible to the properties below, so this
        # is a no-op that just lets the real code path run unmodified.
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
                {
                    "type": "claim",
                    "text": "Example Guideline recommends X.",
                    "citation_ids": ["c1"],
                }
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
        "retrieval": [{"chunk_id": "chunk-1", "score": 0.9}],
        "grounding_report": {"status": "well_supported"},
        "escalation": None,
    }


def _escalated_pipeline_output(*_args: object, **_kwargs: object) -> dict:
    return {
        "observed_outcome": "escalated",
        "escalation": {"trigger_code": "grounding_failure", "message": "could not verify"},
        "retrieval": [],
        "grounding_report": {},
    }


@pytest.fixture(autouse=True)
def _fast_dedup_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("QGEN_DEDUP_THRESHOLD", "0.92")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_prior_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: no patient id has been used before, no embedding exists yet
    (DEVIATIONS.md #114) — the common case for most of these tests. Tests
    that specifically exercise cross-run exclusion override one or both."""
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: set())  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_EXISTING_EMBEDDINGS_FN", lambda session: [])  # noqa: ARG005


def test_already_at_target_skips_without_loading_records(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 5)  # noqa: ARG005
    called = {"load": False}

    def _load(*_args: object, **_kwargs: object) -> list:
        called["load"] = True
        return []

    monkeypatch.setattr(auto_seed, "_LOAD_RECORDS_FN", _load)
    created = auto_seed.run_auto_seed_review_queue(
        _FakeSession(), target_count=5, composition="100,0,0"
    )
    assert created == []
    assert called["load"] is False


def test_no_deidentified_records_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_LOAD_RECORDS_FN", lambda *a, **k: [])  # noqa: ARG005
    created = auto_seed.run_auto_seed_review_queue(
        _FakeSession(), target_count=3, composition="100,0,0"
    )
    assert created == []


def test_tops_up_only_the_remaining_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 2)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=3, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 1  # target 3, 2 already exist -> exactly 1 more
    assert len(session.questions) == 1
    assert len(session.results) == 1
    result = session.results[0]
    assert result.queue_state == "open"
    assert result.eval_question_id == session.questions[0].id


def test_diversity_filter_caps_generation_from_one_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every candidate narrative embeds identically (a stand-in for "the
    model keeps producing near-duplicate phrasing from the same source
    record") -> after the first is accepted, every later one this run is
    rejected as a near-duplicate, so generation stops well short of the
    requested count instead of looping forever or silently duplicating."""
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=5, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 1  # only the first-ever narrative clears the dedup filter


def test_escalated_pipeline_output_persists_with_no_answer_or_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _escalated_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 1
    result = session.results[0]
    assert result.queue_state == "open"
    assert result.observed_outcome == "escalated"
    assert result.citations == []
    assert result.answer_enc is None


def test_transient_gateway_error_during_pipeline_invocation_skips_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEVIATIONS.md #116: a timeout/503 from the real gateway during the
    graph invocation must not crash the whole run — found live, an uncaught
    one stalled generation for ~12 hours. Also asserts nothing is left
    pending in the session (no orphaned EvalQuestion with no Result)."""
    import httpx

    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005

    def _flaky_invoke(*_args: object, **_kwargs: object) -> dict:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _flaky_invoke)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    assert created == []
    assert session.questions == []
    assert session.results == []


def test_transient_gateway_error_during_embedding_skips_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same as above, for the embedding call specifically (DEVIATIONS.md
    #116) — a real, separate failure point from the pipeline invocation."""
    import httpx

    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )

    def _flaky_embed(*_args: object, **_kwargs: object) -> list:
        raise httpx.HTTPStatusError(
            "503", request=httpx.Request("POST", "https://gw/v1/embeddings"), response=None
        )

    monkeypatch.setattr(auto_seed, "_EMBED_FN", _flaky_embed)
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    assert created == []
    assert session.questions == []


def test_run_recovers_after_a_transient_failure_on_an_earlier_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient failure on one candidate must not poison the rest of the
    run — the next candidate still succeeds normally (DEVIATIONS.md #116)."""
    import httpx

    record_a = uuid.uuid4()
    record_b = uuid.uuid4()
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(record_a, RECORD), (record_b, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005

    calls = {"n": 0}

    def _fails_once_then_succeeds(*args: object, **kwargs: object) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out")
        return _well_supported_pipeline_output(*args, **kwargs)

    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _fails_once_then_succeeds)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 1
    assert calls["n"] == 2


def test_excludes_patient_ids_already_used_in_a_prior_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A record that already sourced an auto-generated scenario in some
    earlier run must never source a second one (DEVIATIONS.md #114) — the
    whole pool being excluded here means nothing is generated, same as an
    empty pool."""
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_USED_PATIENT_IDS_FN", lambda session: {RECORD_ID})  # noqa: ARG005

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=3, composition="100,0,0", gateway=_FakeGateway()
    )
    assert created == []
    assert session.questions == []


def test_never_generates_two_scenarios_from_the_same_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only 2 distinct records available but 5 are requested — each record
    sources at most one scenario; the run stops short rather than reusing a
    record (DEVIATIONS.md #114)."""
    record_a = uuid.uuid4()
    record_b = uuid.uuid4()
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(record_a, RECORD), (record_b, RECORD)],  # noqa: ARG005
    )
    counter = {"n": 0}

    def _distinct_embeddings(texts: list[str], **_kwargs: object) -> list[list[float]]:
        # Orthogonal, not just differently-scaled: cosine similarity is
        # scale-invariant, so e.g. [1,0] and [2,0] would still read as a
        # perfect (spurious) near-duplicate match.
        made = []
        for _ in texts:
            counter["n"] += 1
            made.append([1.0, 0.0] if counter["n"] % 2 else [0.0, 1.0])
        return made

    monkeypatch.setattr(auto_seed, "_EMBED_FN", _distinct_embeddings)
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=5, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 2
    assert {q.source_record_id for q in session.questions} == {record_a, record_b}


def test_rejects_near_duplicate_narrative_from_a_different_record_in_the_same_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two different records, but the model produces the same narrative
    (embedding) for both — the second is rejected by the diversity filter,
    not the record-reuse guard: same-record reuse and near-duplicate
    phrasing are independent checks (DEVIATIONS.md #114)."""
    record_a = uuid.uuid4()
    record_b = uuid.uuid4()
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(record_a, RECORD), (record_b, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=2, composition="100,0,0", gateway=_FakeGateway()
    )
    assert len(created) == 1


def test_rejects_a_narrative_matching_a_previously_queued_ones_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even though this run's own `accepted_embeddings` starts from
    `_EXISTING_EMBEDDINGS_FN`, not empty — a prior run's queued narrative
    must still block a matching new one, otherwise raising
    `QGEN_AUTO_SEED_COUNT` and topping up would silently re-accept
    near-duplicates of what's already queued (DEVIATIONS.md #114)."""
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EXISTING_EMBEDDINGS_FN", lambda session: [[1.0, 0.0]])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    created = auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    assert created == []


def test_persists_the_narratives_embedding_in_generator_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`generator_meta["embedding"]` is what `_EXISTING_EMBEDDINGS_FN` reads
    back on a later run (DEVIATIONS.md #114) — verify it's actually written,
    alongside the generator's own existing metadata keys."""
    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[3.0, 4.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    meta = session.questions[0].generator_meta
    assert meta["embedding"] == [3.0, 4.0]
    assert (
        meta["model_id"] == "fake-model"
    )  # the generator's own metadata is preserved, not replaced


def test_well_supported_result_answer_decrypts_to_the_rendered_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.crypto.provider import get_crypto

    monkeypatch.setattr(auto_seed, "_COUNT_EXISTING_AUTO_SEEDED_FN", lambda session: 0)  # noqa: ARG005
    monkeypatch.setattr(
        auto_seed,
        "_LOAD_RECORDS_FN",
        lambda *a, **k: [(RECORD_ID, RECORD)],  # noqa: ARG005
    )
    monkeypatch.setattr(auto_seed, "_EMBED_FN", lambda texts, **k: [[1.0, 0.0] for _ in texts])  # noqa: ARG005
    monkeypatch.setattr(auto_seed, "_INVOKE_PIPELINE_FN", _well_supported_pipeline_output)

    session = _FakeSession()
    auto_seed.run_auto_seed_review_queue(
        session, target_count=1, composition="100,0,0", gateway=_FakeGateway()
    )
    result = session.results[0]
    crypto = get_crypto()
    from app.db.models.eval import result_answer_aad

    plaintext = crypto.decrypt(result.answer_enc, aad=result_answer_aad(result.id))
    assert plaintext.decode("utf-8") == "Example Guideline recommends X."
    assert result.citations[0]["citation_id"] == "c1"
