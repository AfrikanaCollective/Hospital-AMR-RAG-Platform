"""SapBERT / MedCPT loading + pooling for the model-ablation harness
(PRD-110 / ARCH-041, PHASE2-EMBEDDING-ABLATION-PROPOSAL.md §3/§6).

No new dependency: `sentence-transformers` (already in the `local-models`
extra, `backend/pyproject.toml`) pulls in `transformers` + `torch`, which is
all that's needed here — neither SapBERT nor MedCPT is packaged as a
ready-made `SentenceTransformer` model, so this loads the raw checkpoints
via `AutoModel`/`AutoTokenizer` and pools manually.

**Pooling method is UNVERIFIED** (proposal §6): this uses `[CLS]`-token
pooling (`last_hidden_state[:, 0, :]`, L2-normalized), which is SapBERT's and
MedCPT's own documented reference usage as of this writing, but has not been
re-checked against either model's current card. Confirm before trusting a
real (non-stub) run's numbers for anything beyond a rough first look.

`MODEL_ABLATION_BACKEND=stub` (the default) returns deterministic fake
vectors with no model download and no network call — offline-test-only, the
same discipline as `EMBEDDING_BACKEND=stub` elsewhere (CLAUDE.md §5).
`MODEL_ABLATION_BACKEND=local` loads the real checkpoints.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

_STUB_DIM = 32  # arbitrary small fixed dim; only ever compared to itself


def _stub_vector(text: str) -> list[float]:
    """Deterministic fake embedding: sha256(text) seeds a unit-norm vector.
    No model, no download, no network — see module docstring."""
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    v = rng.normal(size=_STUB_DIM)
    v = v / np.linalg.norm(v)
    return v.tolist()


class Encoder:
    """One embedding checkpoint, lazily loaded once and reused. SapBERT is a
    single symmetric checkpoint; MedCPT needs two separate `Encoder`
    instances (query, article) — see `get_medcpt_encoders`."""

    def __init__(self, model_id: str, *, backend: str) -> None:
        self.model_id = model_id
        self.backend = backend
        self._model: Any = None
        self._tokenizer: Any = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # noqa justification: transformers/torch are a multi-GB optional extra
        # (local-models); importing lazily keeps MODEL_ABLATION_BACKEND=stub
        # environments (including offline tests) from needing them at all.
        from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModel.from_pretrained(self.model_id)
        self._model.eval()

    def encode(self, texts: list[str], *, batch_size: int = 16) -> list[list[float]]:
        if self.backend == "stub":
            return [_stub_vector(t) for t in texts]
        if self.backend != "local":
            raise ValueError(f"Unknown MODEL_ABLATION_BACKEND {self.backend!r}")

        import torch  # noqa: PLC0415 - lazy: torch is a multi-GB optional extra

        self._ensure_loaded()
        vectors: list[list[float]] = []
        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                inputs = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    # BERT-family position-embedding limit. Without an explicit
                    # max_length, some tokenizers' own default is unset/too large
                    # and truncation silently doesn't happen — found by a real
                    # chunk (4481 tokens) crashing the forward pass instead of
                    # being truncated (DEVIATIONS.md #131).
                    max_length=512,
                    return_tensors="pt",
                )
                outputs = self._model(**inputs)
                cls = outputs.last_hidden_state[:, 0, :]  # [CLS] pooling — see module docstring
                normed = torch.nn.functional.normalize(cls, p=2, dim=1)
                vectors.extend(normed.tolist())
        return vectors


def _warn_if_unverified(label: str, model_id: str, verified: bool) -> None:
    if not verified:
        logger.warning(
            "%s=%r is an UNVERIFIED placeholder (repo id and pooling method not "
            "re-checked against the model's current card — "
            "PHASE2-EMBEDDING-ABLATION-PROPOSAL.md §6). Confirm before trusting a "
            "real (non-stub) run's numbers, then set the corresponding "
            "*_VERIFIED=true.",
            label,
            model_id,
        )


def get_sapbert_encoder() -> Encoder:
    settings = get_settings()
    _warn_if_unverified(
        "SAPBERT_MODEL_ID", settings.sapbert_model_id, settings.sapbert_model_verified
    )
    return Encoder(settings.sapbert_model_id, backend=settings.model_ablation_backend)


def get_medcpt_encoders() -> tuple[Encoder, Encoder]:
    """Returns `(query_encoder, article_encoder)`. MedCPT is a dual-encoder
    trained with separate checkpoints for queries and articles — unlike
    SapBERT (symmetric), the query and article sides are NOT interchangeable
    (proposal §3)."""
    settings = get_settings()
    _warn_if_unverified(
        "MEDCPT_QUERY_MODEL_ID/MEDCPT_ARTICLE_MODEL_ID",
        f"{settings.medcpt_query_model_id} / {settings.medcpt_article_model_id}",
        settings.medcpt_model_verified,
    )
    query = Encoder(settings.medcpt_query_model_id, backend=settings.model_ablation_backend)
    article = Encoder(settings.medcpt_article_model_id, backend=settings.model_ablation_backend)
    return query, article
