"""LLMGateway — the single path to the self-hosted LLM gateway (ARCH-005).

Constraint #6:
  - model ids come from config; none is hardcoded here;
  - the answer path must not run on the placeholder model id;
  - an unverified id logs a warning (handled in app.config.validate_model_config);
  - fallback routing tries `MODEL_ID_FALLBACKS` in order on gateway
    error/timeout.

Phase 2/3 implement the HTTP calls against `LLM_GATEWAY_URL`. The stub backend
(app.llm.stub) covers offline dev/CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings, get_settings
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatResult:
    text: str
    model_id: str
    used_fallback: bool = False
    usage: dict = field(default_factory=dict)


class LLMGatewayError(RuntimeError):
    pass


class LLMGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Fail closed: the answer path must not start on the placeholder id.
        self.settings.validate_model_config(require_answer_path=True)
        self._model_chain: list[str] = [self.settings.model_id, *self.settings.fallback_model_ids]

    @property
    def model_chain(self) -> list[str]:
        """Primary model id followed by configured fallbacks (ARCH-005)."""
        return list(self._model_chain)

    def chat(self, *, system: str, messages: list[dict], contains_phi: bool = False,
             **params: object) -> ChatResult:
        """Send a chat completion. Tries each model id in `model_chain` in order.

        `contains_phi` is asserted only to make the PHI-egress rule explicit at
        call sites; PHI only ever goes to the configured self-hosted gateway
        (there is no other backend), so this never changes routing — it is a
        guard against a future backend being added carelessly.
        """
        raise NotImplementedError(
            "Phase 2: HTTP call to LLM_GATEWAY_URL with fallback routing (ARCH-005). "
            "Use app.llm.stub for offline dev/CI."
        )

    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError("Phase 2: embeddings via gateway or local backend (ARCH-004)")

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        raise NotImplementedError("Phase 2: cross-encoder rerank (ARCH-012)")
